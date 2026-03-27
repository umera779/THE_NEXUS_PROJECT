

"""app/api/routes/dashboard.py"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi.responses import FileResponse
import os
from app.core.templates import templates
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import create_access_token, generate_otp, hash_pin, verify_pin
from app.models.models import (
    Beneficiary, Checkin, CheckinStatus, Transaction, User, Wallet,
)
from app.models.schemas import (
    AddBeneficiaryRequest, CheckinConfigRequest, DeleteBeneficiaryRequest,
    SetBackupEmailRequest, SetupPinRequest, VerifyBackupEmailRequest,
)
from app.services import email_service, stock_service
from app.services.isw_service import ISWError, find_bank_code, resolve_account

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Dashboard"], prefix="/dashboard")

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
 
def _html(filename: str) -> FileResponse:
    path = os.path.join(TEMPLATES_DIR, filename)
    return FileResponse(path, media_type="text/html")


async def _get_user(db: AsyncSession, user_id: str) -> User:
    """Fetch a fresh user from the current session — avoids detached instance issues."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


# ─── Main Dashboard ───────────────────────────────────────────────────────────

@router.get("", response_class=FileResponse)
async def dashboard(user: User = Depends(get_current_user)):
    return _html("dashboard/index.html")


@router.get("/portfolio")
async def get_portfolio(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    portfolio = await stock_service.get_portfolio_with_current_values(db, user.id)
    total_value = sum(p["current_value"] for p in portfolio)
    total_invested = sum(p["principal_amount"] for p in portfolio)
    total_gain = total_value - total_invested
    return {
        "portfolio": portfolio,
        "summary": {
            "total_invested": round(total_invested, 2),
            "total_value": round(total_value, 2),
            "total_gain_loss": round(total_gain, 2),
            "total_gain_loss_pct": round((total_gain / total_invested) * 100, 2) if total_invested else 0,
        },
    }


@router.get("/wallet")
async def get_wallet(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Wallet).where(Wallet.user_id == user.id))
    wallet = result.scalar_one_or_none()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    txn_result = await db.execute(
        select(Transaction).where(Transaction.user_id == user.id)
        .order_by(Transaction.created_at.desc()).limit(20)
    )
    transactions = txn_result.scalars().all()
    return {
        "balance": float(wallet.balance),
        "currency": wallet.currency,
        "transactions": [
            {"id": t.id, "type": t.transaction_type, "amount": float(t.amount),
             "status": t.status, "reference": t.reference_id,
             "narration": t.narration, "created_at": t.created_at.isoformat()}
            for t in transactions
        ],
    }


# ─── PIN Setup ────────────────────────────────────────────────────────────────

@router.post("/request-pin-otp")
async def request_pin_otp(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    u = await _get_user(db, user.id)
    otp = generate_otp(6)
    u.pin_otp = otp
    u.pin_otp_expires = datetime.now(timezone.utc) + timedelta(minutes=10)
    await db.flush()
    try:
        email_service.send_pin_otp_email(email=u.email, first_name=u.first_name, otp=otp)
    except email_service.EmailError:
        raise HTTPException(status_code=500, detail="Could not send OTP email")
    return {"message": "OTP sent to your email"}


@router.post("/setup-pin")
async def setup_pin(
    payload: SetupPinRequest,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    u = await _get_user(db, user.id)
    now = datetime.now(timezone.utc)
    exp = u.pin_otp_expires
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)

    if not u.pin_otp or u.pin_otp != payload.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    if exp and now > exp:
        raise HTTPException(status_code=400, detail="OTP has expired")

    u.auth_pin_hash = hash_pin(payload.pin)
    u.is_pin_set = True
    u.is_first_login = False
    u.pin_otp = None
    u.pin_otp_expires = None
    await db.flush()

    # Re-issue JWT so the new is_pin_set/is_first_login state is reflected
    # without requiring the user to log out and back in
    new_token = create_access_token({"sub": u.id, "role": u.role})
    response.set_cookie(
        key="access_token",
        value=new_token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {"message": "PIN set successfully"}


# ─── Backup Email ─────────────────────────────────────────────────────────────

@router.post("/backup-email")
async def set_backup_email(
    payload: SetBackupEmailRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    u = await _get_user(db, user.id)

    if not u.is_pin_set or not u.auth_pin_hash:
        raise HTTPException(status_code=400, detail="Please set up your transaction PIN first")

    new_email = str(payload.backup_email).lower().strip()

    # Cannot be same as primary
    if new_email == u.email.lower():
        raise HTTPException(status_code=400, detail="Backup email cannot be same as your primary email")

    # Collect all existing backup emails (verified or not)
    existing_emails = []
    if u.backup_email:
        existing_emails.append(u.backup_email.lower())
    if u.backup_email_2:
        existing_emails.append(u.backup_email_2.lower())

    # Reject if this email is already registered in either slot
    if new_email in existing_emails:
        raise HTTPException(status_code=400, detail="This email is already registered as a backup email")

    # Determine which slot to write into based on payload.slot
    slot = payload.slot
    if slot == 1:
        # Slot 1 can only be set if it hasn't been verified yet (allow updating unverified)
        if u.backup_email and u.is_backup_email_verified:
            raise HTTPException(status_code=400, detail="Slot 1 backup email is already verified. Use slot 2 or contact support.")
    elif slot == 2:
        if not u.backup_email or not u.is_backup_email_verified:
            raise HTTPException(status_code=400, detail="Please add and verify slot 1 backup email first")
        if u.backup_email_2 and u.is_backup_email_2_verified:
            raise HTTPException(status_code=400, detail="Both backup email slots are already verified")

    otp = generate_otp(6)
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)

    if slot == 1:
        u.backup_email = new_email
        u.is_backup_email_verified = False
        u.backup_email_otp = otp
        u.backup_email_otp_expires = expires
    else:
        u.backup_email_2 = new_email
        u.is_backup_email_2_verified = False
        u.backup_email_2_otp = otp
        u.backup_email_2_otp_expires = expires

    await db.flush()

    try:
        email_service.send_backup_email_otp(email=new_email, first_name=u.first_name, otp=otp)
    except email_service.EmailError:
        raise HTTPException(status_code=500, detail="Could not send OTP to backup email")

    return {"message": f"OTP sent to backup email (slot {slot}) for verification"}


@router.post("/backup-email/verify")
async def verify_backup_email(
    payload: VerifyBackupEmailRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    u = await _get_user(db, user.id)

    # PIN check first
    if not u.is_pin_set or not u.auth_pin_hash:
        raise HTTPException(status_code=400, detail="PIN not set up")
    if not verify_pin(payload.pin, u.auth_pin_hash):
        raise HTTPException(status_code=401, detail="Incorrect PIN")

    now = datetime.now(timezone.utc)
    slot = payload.slot

    if slot == 1:
        exp = u.backup_email_otp_expires
        if exp and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if not u.backup_email_otp or u.backup_email_otp != payload.otp:
            raise HTTPException(status_code=400, detail="Invalid OTP")
        if exp and now > exp:
            raise HTTPException(status_code=400, detail="OTP has expired")
        u.is_backup_email_verified = True
        u.backup_email_otp = None
        u.backup_email_otp_expires = None
    else:
        exp = u.backup_email_2_otp_expires
        if exp and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if not u.backup_email_2_otp or u.backup_email_2_otp != payload.otp:
            raise HTTPException(status_code=400, detail="Invalid OTP")
        if exp and now > exp:
            raise HTTPException(status_code=400, detail="OTP has expired")
        u.is_backup_email_2_verified = True
        u.backup_email_2_otp = None
        u.backup_email_2_otp_expires = None

    await db.flush()
    return {"message": f"Backup email (slot {slot}) verified successfully"}


# ─── Beneficiaries ────────────────────────────────────────────────────────────

@router.get("/beneficiaries")
async def list_beneficiaries(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Beneficiary).where(Beneficiary.user_id == user.id))
    beneficiaries = result.scalars().all()
    total_pct = sum(float(b.percentage_share) for b in beneficiaries)
    return {
        "beneficiaries": [
            {"id": b.id, "full_name": b.full_name, "bank_name": b.bank_name,
             "account_number": b.account_number, "percentage_share": float(b.percentage_share),
             "is_verified": b.is_verified, "created_at": b.created_at.isoformat()}
            for b in beneficiaries
        ],
        "total_percentage": total_pct,
    }


@router.post("/beneficiaries/resolve")
async def resolve_beneficiary_account(
    payload: AddBeneficiaryRequest,
    user: User = Depends(get_current_user),
):
    """
    Step 1 of adding a beneficiary — resolve and verify the account details
    before the user enters their PIN.

    Accepts ``account_number`` + ``bank_name`` from the form and calls the
    ISW Marketplace Identity API to confirm the account holder's name.

    Returns a preview dict that the frontend displays in a confirmation card:

        {
            "accountName":   "MICHAEL JOHN DOE",
            "accountNumber": "1000000000",
            "bankName":      "Guaranty Trust Bank",
            "bankCode":      "058"
        }

    No PIN is required at this stage and nothing is written to the database.
    The PIN step happens in POST /beneficiaries once the user confirms.
    """
    try:
        details = await resolve_account(
            account_number=payload.account_number,
            bank_name=payload.bank_name,
        )
    except ISWError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return details


@router.post("/beneficiaries")
async def add_beneficiary(
    payload: AddBeneficiaryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Step 2 of adding a beneficiary — PIN-verified DB write.

    The frontend should call this only after the user has confirmed the
    account details returned by POST /beneficiaries/resolve and entered
    their transaction PIN.

    Expects ``payload.bank_code`` to carry the resolved ISW bank code
    returned by the resolve step (so we don't do a second lookup here).
    Falls back to ``find_bank_code(payload.bank_name)`` for backwards
    compatibility if ``bank_code`` is omitted.
    """
    u = await _get_user(db, user.id)
    if not u.is_pin_set or not u.auth_pin_hash:
        raise HTTPException(status_code=400, detail="Please set up your PIN first")
    if not verify_pin(payload.pin, u.auth_pin_hash):
        raise HTTPException(status_code=401, detail="Incorrect PIN")

    result = await db.execute(select(Beneficiary).where(Beneficiary.user_id == u.id))
    existing = result.scalars().all()
    total_pct = sum(float(b.percentage_share) for b in existing)
    if total_pct + payload.percentage_share > 100:
        raise HTTPException(
            status_code=400,
            detail=f"Total cannot exceed 100%. Currently allocated: {total_pct}%",
        )

    # Prefer the resolved bank_code passed back from the frontend;
    # fall back to static lookup for backwards compatibility.
    bank_code = getattr(payload, "bank_code", None) or find_bank_code(payload.bank_name)
    if not bank_code:
        raise HTTPException(status_code=400, detail=f"Bank '{payload.bank_name}' not recognised")

    # Use the ISW-verified account name if the frontend passed it back,
    # otherwise store what the user typed.
    verified_name = getattr(payload, "account_name", None) or payload.full_name

    bene = Beneficiary(
        user_id=u.id,
        full_name=verified_name,
        bank_name=payload.bank_name,
        bank_code=bank_code,
        account_number=payload.account_number,
        percentage_share=payload.percentage_share,
        is_verified=True,
    )
    db.add(bene)
    await db.flush()
    return {
        "message": "Beneficiary added successfully",
        "beneficiary": {
            "id": bene.id,
            "full_name": bene.full_name,
            "verified_name": verified_name,
            "bank_name": bene.bank_name,
            "account_number": bene.account_number,
            "percentage_share": float(bene.percentage_share),
        },
    }



@router.delete("/beneficiaries/{beneficiary_id}")
async def remove_beneficiary(
    beneficiary_id: str,
    payload: DeleteBeneficiaryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    u = await _get_user(db, user.id)
    if not u.is_pin_set or not u.auth_pin_hash:
        raise HTTPException(status_code=400, detail="PIN not set up")
    if not verify_pin(payload.pin, u.auth_pin_hash):
        raise HTTPException(status_code=401, detail="Incorrect PIN")

    result = await db.execute(
        select(Beneficiary).where(Beneficiary.id == beneficiary_id, Beneficiary.user_id == u.id)
    )
    bene = result.scalar_one_or_none()
    if not bene:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    await db.delete(bene)
    await db.flush()
    return {"message": "Beneficiary removed"}


# ─── Checkin ──────────────────────────────────────────────────────────────────

@router.post("/checkin")
async def do_checkin(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Checkin).where(Checkin.user_id == user.id))
    checkin = result.scalar_one_or_none()
    if not checkin:
        raise HTTPException(status_code=404, detail="Check-in record not found")
    now = datetime.now(timezone.utc)
    checkin.last_checkin_date = now
    checkin.next_due_date = now + timedelta(seconds=checkin.checkin_interval_seconds)
    checkin.status = CheckinStatus.ACTIVE
    await db.flush()
    return {"message": "Check-in recorded", "next_due_date": checkin.next_due_date.isoformat()}


@router.get("/checkin")
async def get_checkin_status(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Checkin).where(Checkin.user_id == user.id))
    checkin = result.scalar_one_or_none()
    if not checkin:
        raise HTTPException(status_code=404, detail="Check-in record not found")
    now = datetime.now(timezone.utc)
    next_due = checkin.next_due_date
    if next_due.tzinfo is None:
        next_due = next_due.replace(tzinfo=timezone.utc)
    grace_deadline = next_due + timedelta(seconds=checkin.grace_period_seconds)
    return {
        "last_checkin_date": checkin.last_checkin_date.isoformat(),
        "next_due_date": checkin.next_due_date.isoformat(),
        "grace_deadline": grace_deadline.isoformat(),
        "checkin_interval_seconds": checkin.checkin_interval_seconds,
        "checkin_interval_days": checkin.checkin_interval_days,
        "grace_period_seconds": checkin.grace_period_seconds,
        "grace_period_days": checkin.grace_period_days,
        "status": checkin.status,
        "seconds_remaining": max(0, (next_due - now).total_seconds()),
        "days_remaining": (next_due - now).days,
        "disbursement_triggered": checkin.disbursement_triggered,
    }

@router.put("/checkin/config")
async def update_checkin_config(payload: CheckinConfigRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    u = await _get_user(db, user.id)
    if not u.is_pin_set or not u.auth_pin_hash:
        raise HTTPException(status_code=400, detail="Please set up your PIN first")
    if not verify_pin(payload.pin, u.auth_pin_hash):
        raise HTTPException(status_code=401, detail="Incorrect PIN")

    result = await db.execute(select(Checkin).where(Checkin.user_id == u.id))
    checkin = result.scalar_one_or_none()
    if not checkin:
        raise HTTPException(status_code=404, detail="Check-in record not found")
    
    now = datetime.now(timezone.utc)

    # Update intervals and reset the last check-in time to NOW
    checkin.last_checkin_date = now
    checkin.checkin_interval_seconds = payload.get_interval_seconds()
    checkin.grace_period_seconds = payload.get_grace_seconds()

    checkin.next_due_date = now + timedelta(seconds=payload.get_interval_seconds()) 

    checkin.status = CheckinStatus.ACTIVE
    checkin.disbursement_triggered = False

    await db.flush()
    return {"message": "Check-in settings updated", "next_due_date": checkin.next_due_date.isoformat()}

@router.get("/balance")
async def get_balance(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Wallet).where(Wallet.user_id == user.id)
    )
    wallet = result.scalar_one_or_none()

    if not wallet:
        return {"balance": 0.0}

    return {
        "balance": float(wallet.balance),
        "currency": wallet.currency
    }

# ─── Profile ──────────────────────────────────────────────────────────────────

@router.get("/profile")
async def get_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    u = await _get_user(db, user.id)
    return {
        "id": u.id,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "email": u.email,
        "phone_number": u.phone_number,
        "kyc_status": u.kyc_status,
        "account_status": u.account_status,
        "is_pin_set": u.is_pin_set,
        "is_first_login": u.is_first_login,
        "backup_email": u.backup_email,
        "is_backup_email_verified": u.is_backup_email_verified,
        "backup_email_2": u.backup_email_2,
        "is_backup_email_2_verified": u.is_backup_email_2_verified,
        "created_at": u.created_at.isoformat(),
    }


@router.get("/fund")
async def fund_wallet_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return templates.TemplateResponse("fund.html", {
        "request": request,
        "user": user,
        "inline_script_url": settings.isw_inline_script_url,
        "base_url": settings.BASE_URL,
    })