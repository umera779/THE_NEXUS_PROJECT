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