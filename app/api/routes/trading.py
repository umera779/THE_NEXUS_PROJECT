"""app/api/routes/trading.py

Stock trading routes for The Nexus.
Allows users to buy and sell Nigerian stocks at current live prices.
All trades settle instantly against the user's wallet balance.

Endpoints
---------
GET  /trading/market
    Returns all available stocks with current prices, sector, change data.

GET  /trading/holdings
    Returns the authenticated user's current holdings (aggregated by symbol)
    with current market value and unrealised P&L.

POST /trading/buy
    Deducts wallet balance and creates/updates an Investment row.
    Body: { stock_symbol, units, pin }

POST /trading/sell
    Credits wallet balance and reduces/removes the Investment row.
    Body: { stock_symbol, units, pin }

GET  /trading/history
    Returns the user's trade transaction history (buy/sell entries).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import verify_pin
from app.models.models import Investment, StockPrice, Transaction, Wallet
from app.models.models import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Trading"], prefix="/trading")


# ─── Schemas ──────────────────────────────────────────────────────────────────

class BuyRequest(BaseModel):
    stock_symbol: str
    units: float
    pin: str

    @field_validator("units")
    @classmethod
    def units_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Units must be greater than zero")
        return round(v, 4)

    @field_validator("pin")
    @classmethod
    def pin_length(cls, v: str) -> str:
        if len(v) != 6 or not v.isdigit():
            raise ValueError("PIN must be exactly 6 digits")
        return v


class SellRequest(BaseModel):
    stock_symbol: str
    units: float
    pin: str

    @field_validator("units")
    @classmethod
    def units_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Units must be greater than zero")
        return round(v, 4)

    @field_validator("pin")
    @classmethod
    def pin_length(cls, v: str) -> str:
        if len(v) != 6 or not v.isdigit():
            raise ValueError("PIN must be exactly 6 digits")
        return v


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_stock(s: StockPrice) -> dict:
    return {
        "symbol":         s.symbol,
        "name":           s.name,
        "current_price":  float(s.current_price),
        "open_price":     float(s.open_price) if s.open_price is not None else None,
        "high_price":     float(s.high_price) if s.high_price is not None else None,
        "low_price":      float(s.low_price) if s.low_price is not None else None,
        "volume":         s.volume,
        "change":         float(s.change) if s.change is not None else None,
        "change_pct":     float(s.change_pct) if s.change_pct is not None else None,
        "trading_status": s.trading_status,
        "sector":         s.sector,
        "updated_at":     s.updated_at.isoformat() if s.updated_at else None,
    }


async def _get_wallet_or_raise(db: AsyncSession, user_id: str) -> Wallet:
    result = await db.execute(select(Wallet).where(Wallet.user_id == user_id))
    wallet = result.scalar_one_or_none()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    if wallet.is_locked:
        raise HTTPException(status_code=403, detail="Your wallet is currently locked")
    return wallet


async def _get_stock_or_raise(db: AsyncSession, symbol: str) -> StockPrice:
    result = await db.execute(
        select(StockPrice).where(StockPrice.symbol == symbol.upper())
    )
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol}' not found")
    if stock.trading_status == 1:
        raise HTTPException(status_code=400, detail=f"{symbol} is currently suspended from trading")
    return stock


async def _get_holding(db: AsyncSession, user_id: str, symbol: str) -> Optional[Investment]:
    """Return the active Investment row for this user+symbol, or None."""
    result = await db.execute(
        select(Investment).where(
            Investment.user_id == user_id,
            Investment.stock_symbol == symbol.upper(),
            Investment.status == "active",
        )
    )
    return result.scalar_one_or_none()


def _verify_user_pin(user: User, raw_pin: str):
    if not user.auth_pin_hash:
        raise HTTPException(status_code=400, detail="Transaction PIN not set up. Please set your PIN first.")
    if not verify_pin(raw_pin, user.auth_pin_hash):
        raise HTTPException(status_code=403, detail="Incorrect PIN")


# ─── GET /trading/market ──────────────────────────────────────────────────────

@router.get("/market")
async def get_market(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all listed stocks with live prices and the user's holdings summary."""
    result = await db.execute(select(StockPrice).order_by(StockPrice.symbol))
    stocks = result.scalars().all()

    # Fetch user's holdings to indicate which stocks they own
    holdings_result = await db.execute(
        select(Investment).where(
            Investment.user_id == user.id,
            Investment.status == "active",
        )
    )
    holdings_map: dict[str, Investment] = {
        inv.stock_symbol: inv for inv in holdings_result.scalars().all()
    }

    market = []
    for s in stocks:
        entry = _fmt_stock(s)
        holding = holdings_map.get(s.symbol)
        if holding:
            entry["owned_units"] = float(holding.units)
            entry["avg_purchase_price"] = float(holding.purchase_price)
        else:
            entry["owned_units"] = 0.0
            entry["avg_purchase_price"] = None
        market.append(entry)

    return {"stocks": market, "count": len(market)}


# ─── GET /trading/holdings ────────────────────────────────────────────────────

@router.get("/holdings")
async def get_holdings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's current holdings enriched with live market data."""
    holdings_result = await db.execute(
        select(Investment).where(
            Investment.user_id == user.id,
            Investment.status == "active",
        )
    )
    investments = holdings_result.scalars().all()

    if not investments:
        return {"holdings": [], "total_invested": 0.0, "total_current_value": 0.0,
                "total_gain_loss": 0.0, "total_gain_loss_pct": 0.0}

    # Fetch live prices for all held symbols in one query
    symbols = [inv.stock_symbol for inv in investments]
    prices_result = await db.execute(
        select(StockPrice).where(StockPrice.symbol.in_(symbols))
    )
    price_map: dict[str, StockPrice] = {s.symbol: s for s in prices_result.scalars().all()}

    holdings = []
    total_invested = 0.0
    total_current_value = 0.0

    for inv in investments:
        stock = price_map.get(inv.stock_symbol)
        current_price = float(stock.current_price) if stock else float(inv.purchase_price)
        units = float(inv.units)
        cost_basis = float(inv.principal_amount)
        current_value = round(units * current_price, 2)
        gain_loss = round(current_value - cost_basis, 2)
        gain_loss_pct = round((gain_loss / cost_basis) * 100, 2) if cost_basis else 0.0

        total_invested += cost_basis
        total_current_value += current_value

        holdings.append({
            "id":                inv.id,
            "stock_symbol":      inv.stock_symbol,
            "stock_name":        inv.stock_name,
            "sector":            stock.sector if stock else None,
            "units":             units,
            "avg_purchase_price": float(inv.purchase_price),
            "cost_basis":        round(cost_basis, 2),
            "current_price":     current_price,
            "current_value":     current_value,
            "gain_loss":         gain_loss,
            "gain_loss_pct":     gain_loss_pct,
            "change":            float(stock.change) if stock and stock.change is not None else None,
            "change_pct":        float(stock.change_pct) if stock and stock.change_pct is not None else None,
            "trading_status":    stock.trading_status if stock else 0,
            "purchased_at":      inv.start_date.isoformat() if inv.start_date else None,
        })

    total_gain_loss = round(total_current_value - total_invested, 2)
    total_gain_loss_pct = round((total_gain_loss / total_invested) * 100, 2) if total_invested else 0.0

    return {
        "holdings": holdings,
        "total_invested": round(total_invested, 2),
        "total_current_value": round(total_current_value, 2),
        "total_gain_loss": total_gain_loss,
        "total_gain_loss_pct": total_gain_loss_pct,
    }


# ─── POST /trading/buy ────────────────────────────────────────────────────────

@router.post("/buy")
async def buy_stock(
    body: BuyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Buy `units` of `stock_symbol` at the current market price.
    Deducts total cost from wallet. Creates or averages into an existing holding.
    """
    _verify_user_pin(user, body.pin)

    stock = await _get_stock_or_raise(db, body.stock_symbol)
    wallet = await _get_wallet_or_raise(db, user.id)

    price = float(stock.current_price)
    total_cost = round(price * body.units, 2)

    if float(wallet.balance) < total_cost:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient wallet balance. Need ₦{total_cost:,.2f}, have ₦{float(wallet.balance):,.2f}",
        )

    now = datetime.now(timezone.utc)

    # ── Update or create holding (weighted-average cost basis) ────────────────
    holding = await _get_holding(db, user.id, stock.symbol)

    if holding:
        # Average down / up: recalculate weighted-average purchase price
        old_units = float(holding.units)
        old_principal = float(holding.principal_amount)
        new_units = old_units + body.units
        new_principal = old_principal + total_cost
        new_avg_price = round(new_principal / new_units, 4)

        holding.units = new_units
        holding.principal_amount = new_principal
        holding.purchase_price = new_avg_price
    else:
        holding = Investment(
            user_id=user.id,
            wallet_id=wallet.id,
            stock_symbol=stock.symbol,
            stock_name=stock.name,
            units=body.units,
            purchase_price=price,
            principal_amount=total_cost,
            interest_rate=0.0,
            start_date=now,
            status="active",
        )
        db.add(holding)

    # ── Deduct wallet ─────────────────────────────────────────────────────────
    wallet.balance = round(float(wallet.balance) - total_cost, 2)

    # ── Record transaction ────────────────────────────────────────────────────
    txn = Transaction(
        user_id=user.id,
        wallet_id=wallet.id,
        transaction_type="stock_buy",
        amount=total_cost,
        status="success",
        reference_id=f"BUY-{uuid.uuid4().hex[:12].upper()}",
        narration=f"Bought {body.units} units of {stock.symbol} @ ₦{price:,.2f}",
        meta={
            "stock_symbol": stock.symbol,
            "stock_name": stock.name,
            "units": body.units,
            "price_per_unit": price,
            "total_cost": total_cost,
        },
    )
    db.add(txn)

    await db.flush()

    logger.info(
        "BUY | user=%s | %s x%.4f @ ₦%.2f = ₦%.2f | wallet_after=₦%.2f",
        user.id, stock.symbol, body.units, price, total_cost, float(wallet.balance),
    )

    return {
        "message": f"Successfully bought {body.units} units of {stock.symbol}",
        "stock_symbol": stock.symbol,
        "units_bought": body.units,
        "price_per_unit": price,
        "total_cost": total_cost,
        "wallet_balance_after": float(wallet.balance),
        "holding_units_total": float(holding.units),
        "reference": txn.reference_id,
    }


# ─── POST /trading/sell ───────────────────────────────────────────────────────

@router.post("/sell")
async def sell_stock(
    body: SellRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Sell `units` of `stock_symbol` at the current market price.
    Credits proceeds to wallet. Reduces or fully closes the holding.
    Realised P&L is recorded in the transaction meta.
    """
    _verify_user_pin(user, body.pin)

    stock = await _get_stock_or_raise(db, body.stock_symbol)
    wallet = await _get_wallet_or_raise(db, user.id)

    holding = await _get_holding(db, user.id, stock.symbol)
    if not holding:
        raise HTTPException(
            status_code=400,
            detail=f"You do not hold any {stock.symbol}",
        )

    owned_units = float(holding.units)
    if body.units > owned_units:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot sell {body.units} units — you only hold {owned_units:.4f}",
        )

    price = float(stock.current_price)
    proceeds = round(price * body.units, 2)

    # Proportional cost basis for the units being sold
    avg_cost_per_unit = float(holding.principal_amount) / owned_units
    cost_of_sold = round(avg_cost_per_unit * body.units, 2)
    realised_pnl = round(proceeds - cost_of_sold, 2)

    # ── Update holding ────────────────────────────────────────────────────────
    remaining_units = round(owned_units - body.units, 4)
    if remaining_units < 0.0001:
        # Full exit — mark holding closed
        holding.units = 0.0
        holding.principal_amount = 0.0
        holding.status = "matured"   # re-use existing enum value for "closed"
    else:
        holding.units = remaining_units
        holding.principal_amount = round(float(holding.principal_amount) - cost_of_sold, 2)

    # ── Credit wallet ─────────────────────────────────────────────────────────
    wallet.balance = round(float(wallet.balance) + proceeds, 2)

    # ── Record transaction ────────────────────────────────────────────────────
    txn = Transaction(
        user_id=user.id,
        wallet_id=wallet.id,
        transaction_type="stock_sell",
        amount=proceeds,
        status="success",
        reference_id=f"SELL-{uuid.uuid4().hex[:12].upper()}",
        narration=f"Sold {body.units} units of {stock.symbol} @ ₦{price:,.2f}",
        meta={
            "stock_symbol": stock.symbol,
            "stock_name": stock.name,
            "units": body.units,
            "price_per_unit": price,
            "proceeds": proceeds,
            "cost_of_sold": cost_of_sold,
            "realised_pnl": realised_pnl,
        },
    )
    db.add(txn)

    await db.flush()

    logger.info(
        "SELL | user=%s | %s x%.4f @ ₦%.2f = ₦%.2f | pnl=₦%.2f | wallet_after=₦%.2f",
        user.id, stock.symbol, body.units, price, proceeds,
        realised_pnl, float(wallet.balance),
    )

    return {
        "message": f"Successfully sold {body.units} units of {stock.symbol}",
        "stock_symbol": stock.symbol,
        "units_sold": body.units,
        "price_per_unit": price,
        "proceeds": proceeds,
        "realised_pnl": realised_pnl,
        "wallet_balance_after": float(wallet.balance),
        "holding_units_remaining": remaining_units if remaining_units >= 0.0001 else 0.0,
        "reference": txn.reference_id,
    }


# ─── GET /trading/history ─────────────────────────────────────────────────────

@router.get("/history")
async def trade_history(
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's buy/sell trade history, most recent first."""
    result = await db.execute(
        select(Transaction)
        .where(
            Transaction.user_id == user.id,
            Transaction.transaction_type.in_(["stock_buy", "stock_sell"]),
        )
        .order_by(Transaction.created_at.desc())
        .limit(min(limit, 200))
    )
    transactions = result.scalars().all()

    return {
        "trades": [
            {
                "id":               t.id,
                "type":             t.transaction_type,
                "reference":        t.reference_id,
                "amount":           float(t.amount),
                "narration":        t.narration,
                "meta":             t.meta or {},
                "created_at":       t.created_at.isoformat(),
            }
            for t in transactions
        ],
        "count": len(transactions),
    }