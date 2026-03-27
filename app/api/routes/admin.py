"""app/api/routes/admin.py"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_admin
from app.core.security import create_access_token, hash_password, verify_password
from app.models.models import Beneficiary, Checkin, Investment, StockPrice, Transaction, User, UserRole, Wallet
from app.models.schemas import CreateAdminRequest, LoginRequest
# REPLACE with:
from app.core.templates import templates

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Admin"], prefix="/admin")
# templates = Jinja2Templates(directory="app/templates")



# ─── Admin Login ──────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})


@router.post("/login")
async def admin_login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Admin access only")

    if user.account_status != "active":
        raise HTTPException(status_code=403, detail="Account suspended")

    token = create_access_token({"sub": user.id, "role": user.role})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {"message": "Admin login successful", "role": user.role}


# ─── Admin Dashboard ──────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    admin: User = Depends(get_current_admin),
):
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "admin": admin,
    })


# ─── Create Admin User (requires admin_secret_key) ───────────────────────────

@router.post("/create-admin")
async def create_admin(
    payload: CreateAdminRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create admin/super_admin users. Requires the ADMIN_SECRET_KEY."""
    if payload.admin_secret_key != settings.ADMIN_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin secret key")

    if payload.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'super_admin'")

    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        phone_number=payload.phone_number,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_email_verified=True,
        account_status="active",
    )
    db.add(user)
    await db.flush()

    return {
        "message": f"{payload.role} account created",
        "user_id": user.id,
        "email": user.email,
        "role": user.role,
    }


# ─── List All Users ───────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.role == UserRole.USER).order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    return {
        "users": [
            {
                "id": u.id,
                "name": f"{u.first_name} {u.last_name}",
                "email": u.email,
                "phone_number": u.phone_number,
                "kyc_status": u.kyc_status,
                "account_status": u.account_status,
                "is_email_verified": u.is_email_verified,
                "is_pin_set": u.is_pin_set,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ],
        "total": len(users),
    }


# ─── User Detail ──────────────────────────────────────────────────────────────

@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    wallet_result = await db.execute(select(Wallet).where(Wallet.user_id == user_id))
    wallet = wallet_result.scalar_one_or_none()

    bene_result = await db.execute(select(Beneficiary).where(Beneficiary.user_id == user_id))
    beneficiaries = bene_result.scalars().all()

    checkin_result = await db.execute(select(Checkin).where(Checkin.user_id == user_id))
    checkin = checkin_result.scalar_one_or_none()

    txn_result = await db.execute(
        select(Transaction).where(Transaction.user_id == user_id).order_by(Transaction.created_at.desc()).limit(10)
    )
    transactions = txn_result.scalars().all()

    return {
        "user": {
            "id": user.id,
            "name": f"{user.first_name} {user.last_name}",
            "email": user.email,
            "phone_number": user.phone_number,
            "backup_email": user.backup_email,
            "is_backup_email_verified": user.is_backup_email_verified,
            "kyc_status": user.kyc_status,
            "account_status": user.account_status,
            "is_email_verified": user.is_email_verified,
            "is_pin_set": user.is_pin_set,
            "paystack_customer_code": user.paystack_customer_code,
            "created_at": user.created_at.isoformat(),
        },
        "wallet": {
            "balance": float(wallet.balance) if wallet else 0,
            "currency": wallet.currency if wallet else "NGN",
            "is_locked": wallet.is_locked if wallet else False,
        } if wallet else None,
        "beneficiaries": [
            {
                "full_name": b.full_name,
                "bank_name": b.bank_name,
                "account_number": b.account_number,
                "percentage_share": float(b.percentage_share),
                "is_verified": b.is_verified,
            }
            for b in beneficiaries
        ],
        "checkin": {
            "last_checkin_date": checkin.last_checkin_date.isoformat(),
            "next_due_date": checkin.next_due_date.isoformat(),
            "interval_days": checkin.checkin_interval_days,
            "grace_period_days": checkin.grace_period_days,
            "status": checkin.status,
            "disbursement_triggered": checkin.disbursement_triggered,
        } if checkin else None,
        "recent_transactions": [
            {
                "type": t.transaction_type,
                "amount": float(t.amount),
                "status": t.status,
                "reference": t.reference_id,
                "created_at": t.created_at.isoformat(),
            }
            for t in transactions
        ],
    }


# ─── Suspend / Unsuspend User ─────────────────────────────────────────────────

@router.post("/users/{user_id}/suspend")
async def suspend_user(
    user_id: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.account_status = "suspended"
    await db.flush()
    return {"message": f"User {user.email} suspended"}


@router.post("/users/{user_id}/unsuspend")
async def unsuspend_user(
    user_id: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.account_status = "active"
    await db.flush()
    return {"message": f"User {user.email} unsuspended"}


# ─── Stock Price Management (read-only — prices come from iTick API) ──────────

@router.get("/stocks")
async def list_stocks(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(StockPrice).order_by(StockPrice.symbol))
    stocks = result.scalars().all()
    return {
        "stocks": [
            {
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
            for s in stocks
        ],
        "source": "iTick NG Market API",
        "note": "Prices are fetched automatically every 15 minutes. Manual editing is disabled.",
    }


@router.post("/stocks/refresh")
async def refresh_stock_prices(admin: User = Depends(get_current_admin)):
    """Manually trigger an immediate market data refresh from iTick."""
    from app.services.market_service import run_market_refresh
    await run_market_refresh()
    return {"message": "Stock prices refreshed from iTick API"}


@router.get("/stats")
async def get_stats(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func

    total_users = (await db.execute(select(func.count(User.id)).where(User.role == UserRole.USER))).scalar()
    verified_users = (await db.execute(select(func.count(User.id)).where(User.is_email_verified == True, User.role == UserRole.USER))).scalar()
    total_wallet_value = (await db.execute(select(func.sum(Wallet.balance)))).scalar() or 0
    total_beneficiaries = (await db.execute(select(func.count(Beneficiary.id)))).scalar()
    triggered_disbursements = (await db.execute(select(func.count(Checkin.id)).where(Checkin.disbursement_triggered == True))).scalar()

    return {
        "total_users": total_users,
        "verified_users": verified_users,
        "total_wallet_value_ngn": float(total_wallet_value),
        "total_beneficiaries": total_beneficiaries,
        "triggered_disbursements": triggered_disbursements,
    }