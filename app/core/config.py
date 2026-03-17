"""app/core/config.py"""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "The Nexus"
    APP_ENV: Literal["development", "production"] = "development"
    SECRET_KEY: str = "insecure-dev-secret-change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/legacy_portal"

    # Paystack
    PAYSTACK_SECRET_KEY: str = ""
    PAYSTACK_PUBLIC_KEY: str = ""
    PAYSTACK_BASE_URL: str = "https://api.paystack.co"
    PAYSTACK_WEBHOOK_SECRET: str = ""

    # Resend
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "The Nexus<noreply@example.com>"

    # Admin
    ADMIN_SECRET_KEY: str = "admin-secret"

    # Check-in
    DEFAULT_CHECKIN_INTERVAL_DAYS: int = 180
    DEFAULT_GRACE_PERIOD_DAYS: int = 30

    # iTick real-time market data
    ITICK_TOKEN: str = ""
    ITICK_BASE_URL: str = "https://api.itick.org"
    STOCK_REFRESH_INTERVAL_MINUTES: int = 15

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()