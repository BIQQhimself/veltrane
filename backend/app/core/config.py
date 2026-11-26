from __future__ import annotations

import base64
import ipaddress
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
    # Peers allowed to set X-Forwarded-For. Everything else is rate-limited by
    # its socket address so the header cannot be used to dodge a limiter.
    trusted_proxies: str = "127.0.0.1,::1"

    secret_key: str = INSECURE_SECRET
    master_encryption_key: str = ""
    kek_version: int = 1

    database_url: str
    redis_url: str = "redis://127.0.0.1:6379/0"
    # Connection pool budget per process. Lower it on hosts whose database caps connections
    # (managed free tiers usually allow far fewer than the defaults).
    db_pool_size: int = 10
    db_max_overflow: int = 20

    access_token_minutes: int = 15
    refresh_token_days: int = 14
    require_email_verification: bool = True
    cookie_secure: bool = False
    # "none" is required when the web app and the API are on different sites
    # (separate hosts/subdomains), where SameSite=Lax cookies are not sent.
    cookie_samesite: str = "lax"
    mfa_issuer: str = "VELTRANE"

    live_trading_enabled: bool = False
    demo_market_data_enabled: bool = True
    paper_taker_fee_bps: float = 10.0
    paper_spread_bps: float = 4.0
    paper_slippage_bps: float = 3.0
    paper_starting_balance: float = 25_000.0
    # Ticks running paper sessions so strategies evaluate new candles unattended.
    # Paper only: this loop has no live execution path.
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 60
    # Fixed-odds binary contracts. Paper only in this build; live routing is not implemented.
    binary_min_stake: float = 10.0
    binary_max_stake: float = 2_000.0
    binary_settlement_grace_seconds: int = 0

    # "off" keeps the payment abstraction present but refuses checkout: used where a
    # deployment has no payment processor connected, which mock cannot cover because
    # mock would grant paid plans for free in production.
    billing_provider: Literal["mock", "stripe", "off"] = "mock"
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    billing_webhook_tolerance_seconds: int = 300

    market_data_source: Literal["ccxt", "demo"] = "ccxt"
    market_data_cache_seconds: int = 20

    # ---- Deriv (broker) -------------------------------------------------------------
    # Endpoints from developers.deriv.com. Overridable so the test suite can point the
    # adapter at a local server that speaks the documented protocol.
    deriv_rest_base: str = "https://api.derivws.com"
    deriv_public_ws_url: str = "wss://api.derivws.com/trading/v1/options/ws/public"
    # App ID registered to VELTRANE. Deriv requires it in the Deriv-App-ID header for PAT auth.
    deriv_app_id: str = ""
    deriv_oauth_client_id: str = ""
    deriv_oauth_redirect_uri: str = ""
    deriv_oauth_auth_url: str = "https://auth.deriv.com/oauth2/auth"
    deriv_oauth_token_url: str = "https://auth.deriv.com/oauth2/token"
    deriv_session_max_failures: int = 5
    deriv_autotrade_runner_enabled: bool = True
    deriv_autotrade_interval_seconds: int = 120
    # Labels Deriv responses as sandbox data. Only meaningful when the endpoints above point at
    # the local protocol mock; it changes nothing about execution, it stops the UI calling a
    # mock "live".
    deriv_sandbox: bool = False

    log_level: str = "INFO"
    admin_email: str = "admin@veltrane.dev"
    admin_password: str = ""

    @field_validator("cors_origins")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @property
    def trusted_proxy_ips(self) -> set[str]:
        return {ip.strip() for ip in self.trusted_proxies.split(",") if ip.strip()}

    def is_trusted_proxy(self, address: str) -> bool:
        """True when X-Forwarded-For may be believed for this peer address.

        Entries may be exact addresses, CIDR blocks, or "*" to trust every peer. "*" is only
        correct when the process cannot be reached except through the platform's proxy: on
        Render, Fly and similar hosts the service only accepts traffic from their edge.
        """
        entries = self.trusted_proxy_ips
        if "*" in entries:
            return True
        if address in entries:
            return True
        try:
            peer = ipaddress.ip_address(address)
        except ValueError:
            return False
        for entry in entries:
            if "/" not in entry:
                continue
            try:
                if peer in ipaddress.ip_network(entry, strict=False):
                    return True
            except ValueError:
                continue
        return False

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

    @field_validator("database_url")
    @classmethod
    def _psycopg_driver(cls, v: str) -> str:
        """Accept the libpq URLs managed hosts hand out.

        This project ships psycopg 3, so a bare ``postgresql://`` would make SQLAlchemy reach
        for psycopg2, which is not installed.
        """
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @field_validator("cookie_samesite")
    @classmethod
    def _check_samesite(cls, v: str) -> str:
        value = v.strip().lower()
        if value not in {"lax", "strict", "none"}:
            raise ValueError("cookie_samesite must be lax, strict or none")
        return value

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise RuntimeError("VELTRANE_COOKIE_SECURE must be true when SameSite=None")
        if self.env == "production":
            if self.secret_key == INSECURE_SECRET or len(self.secret_key) < 32:
                raise RuntimeError("VELTRANE_SECRET_KEY must be a unique 32+ char value in production")
            if not self.cookie_secure:
                raise RuntimeError("VELTRANE_COOKIE_SECURE must be true in production")
            if self.billing_provider == "mock":
                raise RuntimeError(
                    "Mock billing cannot be used in production; set VELTRANE_BILLING_PROVIDER to stripe or off"
                )
            if self.billing_provider == "stripe" and not (self.stripe_secret_key and self.stripe_webhook_secret):
                raise RuntimeError(
                    "Stripe billing in production requires VELTRANE_STRIPE_SECRET_KEY and "
                    "VELTRANE_STRIPE_WEBHOOK_SECRET"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
