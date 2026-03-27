"""app/api/routes/auth.py"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import (
    create_access_token,
    generate_otp,
    hash_password,
    verify_password,
)
from app.models.models import Checkin, User, Wallet
from app.models.schemas import (
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequestModel,
    SignupRequest,
    VerifyEmailRequest,
)
from app.services import stock_service
from app.services import email_service
logger = logging.getLogger(__name__)
router = APIRouter(tags=["Auth"])
templates = Jinja2Templates(directory="app/templates")


# ─── Signup ───────────────────────────────────────────────────────────────────

@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("auth/signup.html", {"request": request})


@router.post("/signup")
async def signup(payload: SignupRequest, db: AsyncSession = Depends(get_db)):
    # Check duplicate email
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Check duplicate phone
    if payload.phone_number:
        existing_phone = await db.execute(
            select(User).where(User.phone_number == payload.phone_number)
        )
        if existing_phone.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Phone number already registered")

    # Create Paystack customer first (fail registration if Paystack fails)

    # Generate email verification code
    code = generate_otp(5)
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)

    user = User(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        phone_number=payload.phone_number,
        password_hash=hash_password(payload.password),
        email_verification_code=code,
        email_verification_expires=expires,
    )
    db.add(user)
    await db.flush()

    # Create wallet
    wallet = Wallet(user_id=user.id)
    db.add(wallet)
    await db.flush()

    now = datetime.now(timezone.utc)
    checkin = Checkin(
        user_id=user.id,
        last_checkin_date=now,
        checkin_interval_seconds=settings.DEFAULT_CHECKIN_INTERVAL_DAYS,
        grace_period_seconds=settings.DEFAULT_GRACE_PERIOD_DAYS,
        next_due_date=now + timedelta(seconds=settings.DEFAULT_CHECKIN_INTERVAL_DAYS),
    )
    db.add(checkin)
    await db.flush()

    # Send verification email
    try:
        email_service.send_verification_email(
            email=user.email,
            first_name=user.first_name,
            code=code,
        )
    except email_service.EmailError as e:
        logger.error("Could not send verification email: %s", e)

    return {"message": "Registration successful. Check your email for a verification code."}


# ─── Verify Email ─────────────────────────────────────────────────────────────

@router.get("/verify-email", response_class=HTMLResponse)
async def verify_email_page(request: Request):
    return templates.TemplateResponse("auth/verify_email.html", {"request": request})


@router.post("/verify-email")
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_email_verified:
        raise HTTPException(status_code=400, detail="Email already verified")

    now = datetime.now(timezone.utc)
    exp = user.email_verification_expires
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)

    if not user.email_verification_code or user.email_verification_code != payload.code:
        raise HTTPException(status_code=400, detail="Invalid verification code")

    if exp and now > exp:
        raise HTTPException(status_code=400, detail="Verification code has expired")

    user.is_email_verified = True
    user.email_verification_code = None
    user.email_verification_expires = None
    await db.flush()

    # Seed stock prices (idempotent)
    await stock_service.seed_stock_prices(db)

    try:
        email_service.send_welcome_email(email=user.email, first_name=user.first_name)
    except email_service.EmailError:
        pass

    return {"message": "Email verified successfully. You can now log in."}


# ─── Login ────────────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request})


@router.post("/login")
async def login(payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_email_verified:
        raise HTTPException(status_code=403, detail="Please verify your email first")

    if user.account_status != "active":
        raise HTTPException(status_code=403, detail="Account is suspended")

    token = create_access_token({"sub": user.id, "role": user.role})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return {
        "message": "Login successful",
        "is_first_login": user.is_first_login,
        "is_pin_set": user.is_pin_set,
        "role": user.role,
    }


# ─── Logout ───────────────────────────────────────────────────────────────────

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Logged out"}


# ─── Password Reset ───────────────────────────────────────────────────────────

@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse("auth/forgot_password.html", {"request": request})


@router.post("/forgot-password")
async def request_password_reset(
    payload: PasswordResetRequestModel,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    # Always return success to avoid email enumeration
    if user and user.is_email_verified:
        code = generate_otp(5)
        expires = datetime.now(timezone.utc) + timedelta(minutes=15)
        user.reset_code = code
        user.reset_code_expires = expires
        await db.flush()

        # Allow reset via backup email if set and verified
        send_to = user.email
        try:
            email_service.send_password_reset_email(
                email=send_to,
                first_name=user.first_name,
                code=code,
            )
        except email_service.EmailError:
            pass

    return {"message": "If that email is registered, a reset code has been sent."}


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request):
    return templates.TemplateResponse("auth/reset_password.html", {"request": request})


@router.post("/reset-password")
async def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    db: AsyncSession = Depends(get_db),
):
    # Allow reset using either primary email or backup email
    result = await db.execute(
        select(User).where(
            (User.email == payload.email) |
            (User.backup_email == payload.email) |
            (User.backup_email_2 == payload.email)
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.now(timezone.utc)
    exp = user.reset_code_expires
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)

    if not user.reset_code or user.reset_code != payload.code:
        raise HTTPException(status_code=400, detail="Invalid reset code")

    if exp and now > exp:
        raise HTTPException(status_code=400, detail="Reset code has expired")

    user.password_hash = hash_password(payload.new_password)
    user.reset_code = None
    user.reset_code_expires = None
    await db.flush()

    return {"message": "Password reset successful. You can now log in."}