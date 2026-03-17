import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


def new_uuid():
    return str(uuid.uuid4())


# ─── Enums ────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class KYCStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class AccountStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class InvestmentStatus(str, enum.Enum):
    ACTIVE = "active"
    MATURED = "matured"
    DISBURSED = "disbursed"


class TransactionType(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"
    DISBURSEMENT = "disbursement"


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REVERSED = "reversed"


class CheckinStatus(str, enum.Enum):
    ACTIVE = "active"
    OVERDUE = "overdue"
    TRIGGERED = "triggered"


# ─── User ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    auth_pin_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(20), default=UserRole.USER)
    kyc_status: Mapped[str] = mapped_column(String(20), default=KYCStatus.PENDING)
    account_status: Mapped[str] = mapped_column(String(30), default=AccountStatus.ACTIVE)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_pin_set: Mapped[bool] = mapped_column(Boolean, default=False)
    backup_email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    is_backup_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    backup_email_2: Mapped[str | None] = mapped_column(String(150), nullable=True)
    is_backup_email_2_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    backup_email_2_otp: Mapped[str | None] = mapped_column(String(10), nullable=True)
    backup_email_2_otp_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paystack_customer_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email_verification_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    email_verification_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reset_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    reset_code_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pin_otp: Mapped[str | None] = mapped_column(String(10), nullable=True)
    pin_otp_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    backup_email_otp: Mapped[str | None] = mapped_column(String(10), nullable=True)
    backup_email_otp_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_first_login: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    wallet: Mapped["Wallet"] = relationship("Wallet", back_populates="user", uselist=False)
    beneficiaries: Mapped[list["Beneficiary"]] = relationship("Beneficiary", back_populates="user")
    investments: Mapped[list["Investment"]] = relationship("Investment", back_populates="user")
    checkin: Mapped["Checkin"] = relationship("Checkin", back_populates="user", uselist=False)
    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="user")


# ─── Wallet ───────────────────────────────────────────────────────────────────

class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    balance: Mapped[float] = mapped_column(Numeric(15, 2), default=0.00)
    currency: Mapped[str] = mapped_column(String(10), default="NGN")
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="wallet")
    investments: Mapped[list["Investment"]] = relationship("Investment", back_populates="wallet")
    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="wallet")


# ─── Beneficiary ──────────────────────────────────────────────────────────────

class Beneficiary(Base):
    __tablename__ = "beneficiaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(150), nullable=False)
    bank_code: Mapped[str] = mapped_column(String(20), nullable=False)
    account_number: Mapped[str] = mapped_column(String(20), nullable=False)
    percentage_share: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    paystack_recipient_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        CheckConstraint("percentage_share > 0", name="chk_percentage_positive"),
    )

    user: Mapped["User"] = relationship("User", back_populates="beneficiaries")


# ─── Investment (simulated portfolio with dummy Nigerian stocks) ───────────────

class Investment(Base):
    __tablename__ = "investments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    wallet_id: Mapped[str] = mapped_column(String(36), ForeignKey("wallets.id", ondelete="CASCADE"))
    stock_symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    stock_name: Mapped[str] = mapped_column(String(100), nullable=False)
    units: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    purchase_price: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    principal_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    interest_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    maturity_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=InvestmentStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="investments")
    wallet: Mapped["Wallet"] = relationship("Wallet", back_populates="investments")


# ─── Stock Price (editable by admin, used for portfolio valuation) ─────────────

class StockPrice(Base):
    __tablename__ = "stock_prices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    current_price: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # iTick real-time fields
    open_price: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    high_price: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    low_price: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    volume: Mapped[int | None] = mapped_column(nullable=True)
    change: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    trading_status: Mapped[int | None] = mapped_column(nullable=True)  # 0=normal,1=suspended
    itick_timestamp_ms: Mapped[int | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ─── Transaction ──────────────────────────────────────────────────────────────

class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    wallet_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("wallets.id", ondelete="CASCADE"), nullable=True)
    transaction_type: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=TransactionStatus.PENDING)
    reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recipient_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    recipient_account: Mapped[str | None] = mapped_column(String(20), nullable=True)
    recipient_bank: Mapped[str | None] = mapped_column(String(150), nullable=True)
    narration: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_amount_positive"),
    )

    user: Mapped["User"] = relationship("User", back_populates="transactions")
    wallet: Mapped["Wallet"] = relationship("Wallet", back_populates="transactions")


# ─── Checkin ──────────────────────────────────────────────────────────────────

class Checkin(Base):
    __tablename__ = "checkins"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    last_checkin_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    checkin_interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    grace_period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    next_due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=CheckinStatus.ACTIVE)
    disbursement_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="checkin")