"""app/core/config.py"""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "Legacy Portal"
    APP_ENV: Literal["development", "production"] = "development"
    SECRET_KEY: str = "insecure-dev-secret-change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"
    BASE_URL: str = "http://localhost:8000"

    # Database
    DATABASE_URL: str

    # ── Interswitch ───────────────────────────────────────────────────────────
    ISW_MERCHANT_CODE: str = "MX275932"
    ISW_PAY_ITEM_ID: str = "Default_Payable_MX275932"
    ISW_WEBHOOK_SECRET: str = ""
    ISW_MODE: str = "TEST"          # "TEST" | "LIVE"

    # Requery / verify endpoint base
    # TEST: https://qa.interswitchng.com
    # LIVE: https://webpay.interswitchng.com
    ISW_REQUERY_BASE_URL: str = "https://qa.interswitchng.com"

    # OAuth2 client credentials for server-side ISW calls (transfers, etc.)
    ISW_CLIENT_ID: str = ""
    ISW_CLIENT_SECRET: str = ""
    ISW_TERMINAL_ID: str = "3PBL0001"
    ISW_INITIATING_ENTITY_CODE: str = "PBL"

    # Resend
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "Legacy Portal<legacyportal@paytime.online>"

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

    @property
    def isw_inline_script_url(self) -> str:
        """URL for the Interswitch Inline Checkout JS widget."""
        if self.ISW_MODE == "LIVE":
            return "https://newwebpay.interswitchng.com/inline-checkout.js"
        return "https://newwebpay.qa.interswitchng.com/inline-checkout.js"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()