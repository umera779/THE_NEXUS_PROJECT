"""main.py — The NexusFastAPI Application"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from app.api.routes import admin, auth, dashboard, market,payment, trading
from app.core.config import settings
from app.core.database import engine
from app.models.models import Base
from app.services.checkin_service import run_checkin_job
from app.services.market_service import initialize_snapshot, run_market_refresh

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
)

scheduler = AsyncIOScheduler()


@app.on_event("startup")
async def startup():
    # Auto-create tables in dev mode
    if not settings.is_production:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created (dev mode)")

    # Seed stock prices
    from app.core.database import AsyncSessionLocal
    from app.services.stock_service import seed_stock_prices
    async with AsyncSessionLocal() as db:
        try:
            await seed_stock_prices(db)
            await db.commit()
        except Exception as e:
            logger.warning("Stock seed skipped: %s", e)

    # Build initial market snapshot from DB
    await initialize_snapshot()

    # Daily check-in job at 08:00
    scheduler.add_job(run_checkin_job, "cron", hour=8, minute=0, id="daily_checkin")

    # Market data refresh every N minutes (default 15)
    scheduler.add_job(
        run_market_refresh,
        "interval",
        minutes=settings.STOCK_REFRESH_INTERVAL_MINUTES,
        id="market_refresh",
    )

    scheduler.start()
    logger.info(
        "Scheduler started — check-in @ 08:00, market refresh every %d min",
        settings.STOCK_REFRESH_INTERVAL_MINUTES,
    )

    # Kick off one immediate refresh so prices are current on startup
    if settings.ITICK_TOKEN:
        import asyncio
        asyncio.create_task(run_market_refresh())


@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown(wait=False)


# ─── Routes ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(admin.router)
app.include_router(market.router)
app.include_router(payment.router)
app.include_router(trading.router)




@app.get("/")
async def root():
    return RedirectResponse(url="/login")



from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.core.dependencies import get_current_user
 
templates = Jinja2Templates(directory="app/templates")
 
@app.get("/trade", response_class=HTMLResponse)
async def trade_page(request: Request, user = Depends(get_current_user)):
    return templates.TemplateResponse("trading.html", {"request": request, "user": user})

@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}