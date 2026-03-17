"""app/services/market_service.py
Background job that:
  1. Fetches real-time quotes from iTick every 15 minutes
  2. Updates StockPrice table in DB
  3. Broadcasts price updates to all connected SSE clients (live dashboard)
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import AsyncSessionLocal
from app.models.models import StockPrice
from app.services import itick_service

logger = logging.getLogger(__name__)

# ─── SSE subscriber registry ──────────────────────────────────────────────────
# Each connected dashboard client registers a queue here.
# When prices update we push the new snapshot to every queue.
_subscribers: list[asyncio.Queue] = []

# Latest price snapshot — served immediately to new SSE connections
_latest_snapshot: dict = {}


def _register_subscriber() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=10)
    _subscribers.append(q)
    return q


def _unregister_subscriber(q: asyncio.Queue):
    try:
        _subscribers.remove(q)
    except ValueError:
        pass


def _broadcast(data: dict):
    """Push price update to all connected SSE clients."""
    global _latest_snapshot
    _latest_snapshot = data
    dead = []
    for q in _subscribers:
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _unregister_subscriber(q)


async def sse_stream(user_id: str) -> AsyncGenerator[str, None]:
    """
    Async generator for SSE endpoint.
    Immediately sends latest snapshot then streams updates as they arrive.
    """
    q = _register_subscriber()
    try:
        # Send current snapshot immediately on connect
        if _latest_snapshot:
            yield f"data: {json.dumps(_latest_snapshot)}\n\n"

        while True:
            try:
                data = await asyncio.wait_for(q.get(), timeout=30)
                yield f"data: {json.dumps(data)}\n\n"
            except asyncio.TimeoutError:
                # Keepalive ping every 30s so the connection doesn't drop
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        _unregister_subscriber(q)


# ─── DB update ────────────────────────────────────────────────────────────────

async def _update_prices_in_db(quotes: dict[str, dict]):
    """Write fetched quotes into the stock_prices table."""
    async with AsyncSessionLocal() as db:
        try:
            for symbol, quote in quotes.items():
                price = quote.get("last_price", 0)
                if price <= 0:
                    continue

                result = await db.execute(
                    select(StockPrice).where(StockPrice.symbol == symbol)
                )
                stock = result.scalar_one_or_none()
                now = datetime.now(timezone.utc)
                if stock:
                    stock.current_price = price
                    stock.open_price = quote.get("open")
                    stock.high_price = quote.get("high")
                    stock.low_price = quote.get("low")
                    stock.volume = quote.get("volume")
                    stock.change = quote.get("change")
                    stock.change_pct = quote.get("change_pct")
                    stock.trading_status = quote.get("trading_status")
                    stock.itick_timestamp_ms = quote.get("timestamp_ms")
                    stock.updated_at = now
                else:
                    stock = StockPrice(
                        symbol=symbol,
                        name=quote.get("symbol", symbol),
                        current_price=price,
                        open_price=quote.get("open"),
                        high_price=quote.get("high"),
                        low_price=quote.get("low"),
                        volume=quote.get("volume"),
                        change=quote.get("change"),
                        change_pct=quote.get("change_pct"),
                        trading_status=quote.get("trading_status"),
                        itick_timestamp_ms=quote.get("timestamp_ms"),
                    )
                    db.add(stock)

            await db.commit()
            logger.info("Stock prices updated in DB for: %s", list(quotes.keys()))
        except Exception as e:
            await db.rollback()
            logger.error("Failed to update stock prices in DB: %s", e)


# ─── Price snapshot builder ───────────────────────────────────────────────────

async def _build_snapshot() -> dict:
    """
    Build the full price snapshot from DB (includes all stocks, not just active ones).
    This is what gets broadcast to SSE clients.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(StockPrice))
        stocks = result.scalars().all()
        return {
            "type": "price_update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prices": {
                s.symbol: {
                    "symbol":          s.symbol,
                    "name":            s.name,
                    "current_price":   float(s.current_price),
                    "open_price":      float(s.open_price) if s.open_price is not None else None,
                    "high_price":      float(s.high_price) if s.high_price is not None else None,
                    "low_price":       float(s.low_price) if s.low_price is not None else None,
                    "volume":          s.volume,
                    "change":          float(s.change) if s.change is not None else None,
                    "change_pct":      float(s.change_pct) if s.change_pct is not None else None,
                    "trading_status":  s.trading_status,
                    "updated_at":      s.updated_at.isoformat() if s.updated_at else None,
                }
                for s in stocks
            }
        }


# ─── Main refresh job ─────────────────────────────────────────────────────────

async def run_market_refresh():
    """
    Called by APScheduler every 15 minutes.
    Fetches quotes → updates DB → broadcasts to SSE clients.
    """
    logger.info("Market refresh: fetching real-time quotes...")
    quotes = await itick_service.fetch_all_active_quotes()

    if quotes:
        await _update_prices_in_db(quotes)
        logger.info("Market refresh: updated %d stocks", len(quotes))
    else:
        logger.warning("Market refresh: no quotes received from iTick")

    # Always broadcast a snapshot (uses DB prices — includes fallback/seed prices too)
    snapshot = await _build_snapshot()
    _broadcast(snapshot)
    logger.info("Market refresh: broadcast sent to %d subscribers", len(_subscribers))


async def initialize_snapshot():
    """Build the initial snapshot from DB on startup so SSE clients get data immediately."""
    global _latest_snapshot
    snapshot = await _build_snapshot()
    _latest_snapshot = snapshot
    logger.info("Market service: initial snapshot loaded (%d stocks)", len(snapshot.get("prices", {})))