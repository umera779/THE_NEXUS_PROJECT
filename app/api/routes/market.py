"""app/api/routes/market.py
SSE endpoint for real-time stock price streaming.
Also exposes a REST endpoint to get current prices + manually trigger a refresh.
"""
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_current_user
from app.models.models import User
from app.services import market_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Market"], prefix="/market")


@router.get("/stream")
async def price_stream(user: User = Depends(get_current_user)):
    """
    SSE endpoint. Frontend connects here to receive real-time price updates.
    Each message is a JSON object: { type, timestamp, prices: {SYMBOL: {symbol, name, current_price}} }
    """
    return StreamingResponse(
        market_service.sse_stream(user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
            "Connection": "keep-alive",
        },
    )


@router.get("/prices")
async def get_current_prices(user: User = Depends(get_current_user)):
    """REST fallback: returns latest price snapshot from DB."""
    from app.core.database import AsyncSessionLocal
    from app.models.models import StockPrice
    from sqlalchemy.future import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(StockPrice).order_by(StockPrice.symbol))
        stocks = result.scalars().all()
        return {
            "prices": {
                s.symbol: {
                    "symbol": s.symbol,
                    "name": s.name,
                    "current_price": float(s.current_price),
                    "sector": s.sector,
                    "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                }
                for s in stocks
            }
        }


@router.post("/refresh")
async def manual_refresh(user: User = Depends(get_current_user)):
    """Manually trigger a market data refresh (useful for testing)."""
    await market_service.run_market_refresh()
    return {"message": "Market data refreshed"}