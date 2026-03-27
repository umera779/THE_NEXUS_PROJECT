"""app/models/schemas.py"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator


# ─── Auth ─────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone_number: str
    password: str
    confirm_password: str

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v, info):
        if info.data.get("password") and v != info.data["password"]:
            raise ValueError("Passwords do not match")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequestModel(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str
    confirm_password: str

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v, info):
        if info.data.get("new_password") and v != info.data["new_password"]:
            raise ValueError("Passwords do not match")
        return v


# ─── PIN ──────────────────────────────────────────────────────────────────────

class SetupPinRequest(BaseModel):
    pin: str
    confirm_pin: str
    otp: str

    @field_validator("pin")
    @classmethod
    def pin_length(cls, v):
        if len(v) != 6 or not v.isdigit():
            raise ValueError("PIN must be exactly 6 digits")
        return v

    @field_validator("confirm_pin")
    @classmethod
    def pins_match(cls, v, info):
        if info.data.get("pin") and v != info.data["pin"]:
            raise ValueError("PINs do not match")
        return v


class RequestPinOTPRequest(BaseModel):
    pass  # just needs the authenticated user


# ─── Backup Email ─────────────────────────────────────────────────────────────

class SetBackupEmailRequest(BaseModel):
    backup_email: EmailStr
    slot: int = 1  # 1 or 2

    @field_validator("slot")
    @classmethod
    def valid_slot(cls, v):
        if v not in (1, 2):
            raise ValueError("Slot must be 1 or 2")
        return v


class VerifyBackupEmailRequest(BaseModel):
    otp: str
    pin: str
    slot: int = 1

    @field_validator("pin")
    @classmethod
    def pin_length(cls, v):
        if len(v) != 6 or not v.isdigit():
            raise ValueError("PIN must be 6 digits")
        return v

    @field_validator("slot")
    @classmethod
    def valid_slot(cls, v):
        if v not in (1, 2):
            raise ValueError("Slot must be 1 or 2")
        return v


# ─── Beneficiary ──────────────────────────────────────────────────────────────

class AddBeneficiaryRequest(BaseModel):
    full_name: str
    bank_name: str
    account_number: str
    percentage_share: float
    pin: str
    bank_code: Optional[str] = None      
    account_name: Optional[str] = None   

    @field_validator("percentage_share")
    @classmethod
    def valid_percentage(cls, v):
        if v <= 0 or v > 100:
            raise ValueError("Percentage must be between 0.01 and 100")
        return v

    @field_validator("pin")
    @classmethod
    def pin_length(cls, v):
        if len(v) != 6 or not v.isdigit():
            raise ValueError("PIN must be 6 digits")
        return v


class BeneficiaryResponse(BaseModel):
    id: str
    full_name: str
    bank_name: str
    account_number: str
    percentage_share: float
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class DeleteBeneficiaryRequest(BaseModel):
    pin: str

    @field_validator("pin")
    @classmethod
    def pin_length(cls, v):
        if len(v) != 6 or not v.isdigit():
            raise ValueError("PIN must be 6 digits")
        return v


# ─── Checkin ──────────────────────────────────────────────────────────────────

class CheckinConfigRequest(BaseModel):
    checkin_interval_days: int
    grace_period_days: int
    pin: str

    @field_validator("checkin_interval_days")
    @classmethod
    def valid_interval(cls, v):
        if v < 30 or v > 730:
            raise ValueError("Interval must be between 30 and 730 days")
        return v

    @field_validator("pin")
    @classmethod
    def pin_length(cls, v):
        if len(v) != 6 or not v.isdigit():
            raise ValueError("PIN must be 6 digits")
        return v


# ─── Admin ────────────────────────────────────────────────────────────────────

class CreateAdminRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone_number: str
    password: str
    role: str = "admin"
    admin_secret_key: str


class UpdateStockPriceRequest(BaseModel):
    symbol: str
    new_price: float

    @field_validator("new_price")
    @classmethod
    def valid_price(cls, v):
        if v <= 0:
            raise ValueError("Price must be positive")
        return v


# ─── Investment response ──────────────────────────────────────────────────────

class InvestmentResponse(BaseModel):
    id: str
    stock_symbol: str
    stock_name: str
    units: float
    purchase_price: float
    principal_amount: float
    status: str
    current_value: Optional[float] = None
    gain_loss: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class FundWalletRequest(BaseModel):
    amount_kobo: int

    @field_validator("amount_kobo")
    @classmethod
    def amount_must_be_positive(cls, v: int) -> int:
        if v < 10000:  # minimum ₦100
            raise ValueError("Minimum funding amount is ₦100 (10 000 kobo)")
        return v


class InitiatePaymentResponse(BaseModel):
    """
    Returned by POST /fund/initiate.
    The front-end passes these values directly to window.webpayCheckout().
    """
    txn_ref: str
    amount_kobo: int
    merchant_code: str
    pay_item_id: str
    customer_email: str
    mode: str                    # "TEST" | "LIVE"
    site_redirect_url: str
    inline_script_url: str       # URL of the ISW inline checkout JS to load


# ── Transaction ───────────────────────────────────────────────────────────────

class TransactionOut(BaseModel):
    id: int
    txn_ref: str
    amount_kobo: int
    status: str
    confirmed_via: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Webhook ───────────────────────────────────────────────────────────────────

class ISWWebhookData(BaseModel):
    """
    Interswitch sends a JSON body on the configured webhook URL.
    Fields vary slightly between TEST and LIVE; treat everything as optional
    and rely on server-side requery to confirm payment.
    """
    ResponseCode: Optional[str] = None
    Amount: Optional[int] = None                  # in kobo
    MerchantReference: Optional[str] = None       # our txn_ref
    PaymentReference: Optional[str] = None        # ISW's reference
    RetrievalReferenceNumber: Optional[str] = None
    TransactionDate: Optional[str] = None


class ISWWebhookPayload(BaseModel):
    """Top-level Interswitch webhook envelope."""
    event: Optional[str] = None
    data: Optional[ISWWebhookData] = None



class BuyStockRequest(BaseModel):
    """POST /trading/buy"""
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
 
 
class SellStockRequest(BaseModel):
    """POST /trading/sell"""
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
 
 
class TradeResponse(BaseModel):
    """Generic response for buy / sell confirmations."""
    message: str
    stock_symbol: str
    units_bought: float | None = None
    units_sold: float | None = None
    price_per_unit: float
    total_cost: float | None = None
    proceeds: float | None = None
    realised_pnl: float | None = None
    wallet_balance_after: float
    reference: str