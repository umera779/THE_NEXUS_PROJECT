"""app/services/itick_service.py
iTick API wrapper for Nigerian (NG) stock market real-time quotes.
Fetches prices every 15 minutes and updates the StockPrice table.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── Tracked stocks (up to 5 active, easily expandable) ──────────────────────
# Set active=True for stocks to fetch from iTick.
# active=False stocks fall back to DB/seed price.
TRACKED_STOCKS = [
    {"symbol": "DANGCEM",  "name": "Dangote Cement Plc",          "active": True},
    {"symbol": "MTNN",     "name": "MTN Nigeria Comm Plc",         "active": True},
    {"symbol": "GTCO",     "name": "Guaranty Trust Holding Co",    "active": True},
    {"symbol": "ZENITHBANK","name": "Zenith Bank Plc",             "active": True},
    {"symbol": "AIRTELAF", "name": "Airtel Africa Plc",            "active": True},
    # ── Expand by setting active=True below ──────────────────────────────────
    {"symbol": "ACCESS",   "name": "Access Holdings Plc",          "active": False},
    {"symbol": "UBA",      "name": "United Bank for Africa Plc",   "active": False},
    {"symbol": "BUACEMENT","name": "BUA Cement Plc",               "active": False},
    {"symbol": "SEPLAT",   "name": "Seplat Energy Plc",            "active": False},
    {"symbol": "NESTLE",   "name": "Nestle Nigeria Plc",           "active": False},
    {"symbol": "FLOURMILL","name": "Flour Mills of Nigeria Plc",   "active": False},
    {"symbol": "NB",       "name": "Nigerian Breweries Plc",       "active": False},
]

ACTIVE_SYMBOLS = [s["symbol"] for s in TRACKED_STOCKS if s["active"]]


class ITickError(Exception):
    pass


async def get_realtime_quote(symbol: str) -> Optional[dict]:
    """
    Fetch a single real-time quote from iTick NG market.
    Returns a dict with Symbol, Last Price, Change, Change % etc. or None on failure.
    """
    if not settings.ITICK_TOKEN:
        logger.warning("ITICK_TOKEN not configured — skipping real-time fetch for %s", symbol)
        return None

    headers = {
        "accept": "application/json",
        "token": settings.ITICK_TOKEN,
    }
    params = {"region": "NG", "code": symbol.upper()}

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{settings.ITICK_BASE_URL}/stock/quote",
                    headers=headers,
                    params=params,
                )
            if r.status_code == 200:
                result = r.json()
                if result.get("code") == 0 and "data" in result:
                    q = result["data"]
                    return {
                        "symbol":         q.get("s", symbol),
                        "last_price":     float(q.get("ld", 0)),
                        "open":           float(q.get("o", 0)),
                        "high":           float(q.get("h", 0)),
                        "low":            float(q.get("l", 0)),
                        "volume":         int(q.get("v", 0)),
                        "change":         float(q.get("ch", 0)),
                        "change_pct":     float(q.get("chp", 0)),
                        "timestamp_ms":   q.get("t"),
                        "trading_status": q.get("ts", 0),
                    }
                else:
                    logger.warning("iTick: no data for %s — %s", symbol, result.get("msg"))
                    return None
            else:
                logger.warning("iTick: HTTP %s for %s — attempt %d", r.status_code, symbol, attempt + 1)
                await asyncio.sleep(1.5)
        except httpx.TimeoutException:
            logger.warning("iTick: timeout for %s — attempt %d", symbol, attempt + 1)
            await asyncio.sleep(1.5)
        except Exception as e:
            logger.error("iTick: unexpected error for %s: %s", symbol, e)
            return None

    return None


async def fetch_all_active_quotes() -> dict[str, dict]:
    """
    Fetch quotes for all active tracked stocks concurrently.
    Returns {symbol: quote_dict} for successful fetches only.
    """
    tasks = {symbol: get_realtime_quote(symbol) for symbol in ACTIVE_SYMBOLS}
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    quotes = {}
    for symbol, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            logger.error("Quote fetch failed for %s: %s", symbol, result)
        elif result is not None:
            quotes[symbol] = result
        else:
            logger.warning("No quote returned for %s", symbol)
    return quotes