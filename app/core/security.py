"""app/core/security.py"""
import hashlib
import hmac
import random
import secrets
import string
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


# ─── Password ─────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ─── PIN ──────────────────────────────────────────────────────────────────────

def hash_pin(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_pin(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ─── JWT ──────────────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


# ─── OTP / Codes ─────────────────────────────────────────────────────────────

def generate_otp(length: int = 5) -> str:
    """Generate numeric OTP (5-digit for email verification, 6-digit for PIN OTP)."""
    return "".join(random.choices(string.digits, k=length))


def generate_reference(prefix: str = "LGP") -> str:
    return f"{prefix}-{''.join(secrets.token_hex(8).upper())}"


# ─── Paystack webhook verification ───────────────────────────────────────────

def verify_paystack_signature(body: bytes, signature: str) -> bool:
    secret = settings.PAYSTACK_WEBHOOK_SECRET.encode()
    expected = hmac.new(secret, body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)