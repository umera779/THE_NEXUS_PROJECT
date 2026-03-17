"""app/services/stock_service.py
Nigerian stock market simulation data.
Stocks are seeded on startup with editable prices (admin can update them).
"""
from datetime import datetime, timedelta, timezone
import random

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import Investment, StockPrice, Wallet

NIGERIAN_STOCKS = [
    {"symbol": "DANGCEM", "name": "Dangote Cement Plc", "price": 780.00, "sector": "Industrial Goods"},
    {"symbol": "MTNN",    "name": "MTN Nigeria Comm Plc", "price": 240.00, "sector": "ICT"},
    {"symbol": "AIRTELAF","name": "Airtel Africa Plc", "price": 2200.00, "sector": "ICT"},
    {"symbol": "GTCO",    "name": "Guaranty Trust Holding Co", "price": 58.00, "sector": "Financial Services"},
    {"symbol": "ZENITHBANK","name": "Zenith Bank Plc", "price": 47.00, "sector": "Financial Services"},
    {"symbol": "ACCESS",  "name": "Access Holdings Plc", "price": 22.00, "sector": "Financial Services"},
    {"symbol": "UBA",     "name": "United Bank for Africa Plc", "price": 28.00, "sector": "Financial Services"},
    {"symbol": "BUACEMENT","name": "BUA Cement Plc", "price": 115.00, "sector": "Industrial Goods"},
    {"symbol": "SEPLAT",  "name": "Seplat Energy Plc", "price": 4200.00, "sector": "Oil and Gas"},
    {"symbol": "NESTLE",  "name": "Nestle Nigeria Plc", "price": 1450.00, "sector": "Consumer Goods"},
    {"symbol": "FLOURMILL","name": "Flour Mills of Nigeria Plc", "price": 56.00, "sector": "Consumer Goods"},
    {"symbol": "NB",      "name": "Nigerian Breweries Plc", "price": 32.00, "sector": "Consumer Goods"},
]


async def seed_stock_prices(db: AsyncSession):
    """Seed default stock prices if not already present."""
    for stock in NIGERIAN_STOCKS:
        result = await db.execute(
            select(StockPrice).where(StockPrice.symbol == stock["symbol"])
        )
        existing = result.scalar_one_or_none()
        if not existing:
            sp = StockPrice(
                symbol=stock["symbol"],
                name=stock["name"],
                current_price=stock["price"],
                sector=stock["sector"],
            )
            db.add(sp)
    await db.flush()


async def seed_dummy_portfolio(db: AsyncSession, user_id: str, wallet_id: str):
    """Assign a random portfolio of 3-5 stocks to a new user for simulation."""
    chosen = random.sample(NIGERIAN_STOCKS, k=random.randint(3, 5))
    now = datetime.now(timezone.utc)
    total_invested = 0.0

    for stock in chosen:
        units = round(random.uniform(10, 200), 2)
        purchase_price = stock["price"] * random.uniform(0.80, 1.10)
        principal = round(units * purchase_price, 2)
        total_invested += principal

        inv = Investment(
            user_id=user_id,
            wallet_id=wallet_id,
            stock_symbol=stock["symbol"],
            stock_name=stock["name"],
            units=units,
            purchase_price=round(purchase_price, 2),
            principal_amount=principal,
            interest_rate=round(random.uniform(0.05, 0.15), 4),
            start_date=now - timedelta(days=random.randint(30, 365)),
            maturity_date=now + timedelta(days=random.randint(180, 730)),
            status="active",
        )
        db.add(inv)

    await db.flush()
    return total_invested


async def get_portfolio_with_current_values(
    db: AsyncSession, user_id: str
) -> list[dict]:
    """Return investments enriched with current stock prices."""
    inv_result = await db.execute(
        select(Investment).where(Investment.user_id == user_id)
    )
    investments = inv_result.scalars().all()

    stock_result = await db.execute(select(StockPrice))
    prices = {sp.symbol: sp.current_price for sp in stock_result.scalars().all()}

    portfolio = []
    for inv in investments:
        current_price = prices.get(inv.stock_symbol, float(inv.purchase_price))
        current_value = float(inv.units) * float(current_price)
        gain_loss = current_value - float(inv.principal_amount)
        gain_loss_pct = (gain_loss / float(inv.principal_amount)) * 100 if inv.principal_amount else 0

        portfolio.append({
            "id": inv.id,
            "stock_symbol": inv.stock_symbol,
            "stock_name": inv.stock_name,
            "units": float(inv.units),
            "purchase_price": float(inv.purchase_price),
            "principal_amount": float(inv.principal_amount),
            "current_price": float(current_price),
            "current_value": round(current_value, 2),
            "gain_loss": round(gain_loss, 2),
            "gain_loss_pct": round(gain_loss_pct, 2),
            "status": inv.status,
            "start_date": inv.start_date.isoformat() if inv.start_date else None,
            "maturity_date": inv.maturity_date.isoformat() if inv.maturity_date else None,
        })

    return portfolio
