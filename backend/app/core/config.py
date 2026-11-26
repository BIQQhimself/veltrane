from __future__ import annotations

import base64
import secrets
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_SECRET = "change-me-development-only-0000000000000000000000000000"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VELTRANE_",
        env_file=(".env", "../.env"),
        extra="ignore",
        # Never echo setting values (secrets included) in validation errors.
        hide_input_in_errors=True,
    )

    env: Literal["development", "test", "production"] = "development"
    app_name: str = "VELTRANE"
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    secret_key: str = INSECURE_SECRET
    master_encryption_key: str = ""
    kek_version: int = 1

    database_url: str
    redis_url: str = "redis://127.0.0.1:6379/0"

    access_token_minutes: int = 15
    refresh_token_days: int = 14
    require_email_verification: bool = True
    cookie_secure: bool = False
    mfa_issuer: str = "VELTRANE"

    live_trading_enabled: bool = False
    demo_market_data_enabled: bool = True
    paper_taker_fee_bps: float = 10.0
    paper_spread_bps: float = 4.0
    paper_slippage_bps: float = 3.0
    paper_starting_balance: float = 25_000.0

    billing_provider: Literal["mock", "stripe"] = "mock"
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    billing_webhook_tolerance_seconds: int = 300

    market_data_source: Literal["ccxt", "demo"] = "ccxt"
    market_data_cache_seconds: int = 20

    log_level: str = "INFO"
    admin_email: str = "admin@veltrane.local"
    admin_password: str = ""

    @field_validator("cors_origins")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    def ensure_master_key(self) -> bytes:
        """Return the 32-byte KEK, generating an ephemeral one outside production."""
        if self.master_encryption_key:
            raw = base64.b64decode(self.master_encryption_key)
            if len(raw) != 32:
                raise RuntimeError("VELTRANE_MASTER_ENCRYPTION_KEY must decode to 32 bytes")
            return raw
        if self.is_production:
            raise RuntimeError("VELTRANE_MASTER_ENCRYPTION_KEY is required in production")
        # Ephemeral key: credentials created in this process cannot be read after restart.
        return secrets.token_bytes(32)

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.env == "production":
            if self.secret_key == INSECURE_SECRET or len(self.secret_key) < 32:
                raise RuntimeError("VELTRANE_SECRET_KEY must be a unique 32+ char value in production")
            if not self.cookie_secure:
                raise RuntimeError("VELTRANE_COOKIE_SECURE must be true in production")
            if self.billing_provider == "mock":
                raise RuntimeError("Mock billing cannot be used in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
