from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


# ----------------------------- auth -----------------------------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=2, max_length=160)
    country: str | None = Field(default=None, max_length=2)
    terms_version: str = Field(default="terms-2026-01", max_length=24)
    accept_terms: bool = True

    @field_validator("accept_terms")
    @classmethod
    def _terms(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must accept the terms to create an account.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class MfaLoginRequest(BaseModel):
    mfa_token: str
    code: str = Field(min_length=4, max_length=32)


class VerifyEmailRequest(BaseModel):
    token: str


class EmailOnlyRequest(BaseModel):
    email: EmailStr


class PasswordResetRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=12, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=128)


class MfaEnableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class MfaDisableRequest(BaseModel):
    password: str


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    timezone: str | None = Field(default=None, max_length=64)
    country: str | None = Field(default=None, max_length=2)
    marketing_opt_in: bool | None = None


class RiskProfileUpdate(BaseModel):
    experience: Literal["beginner", "intermediate", "advanced"] = "beginner"
    risk_appetite: Literal["conservative", "balanced", "aggressive"] = "balanced"
    max_drawdown_pct: float = Field(default=10.0, ge=1, le=50)
    max_position_pct: float = Field(default=5.0, ge=0.5, le=25)
    preferred_markets: list[str] = Field(default_factory=lambda: ["crypto"])
    horizon: Literal["scalping", "day", "swing", "position"] = "swing"


class OnboardingUpdate(BaseModel):
    step: int = Field(ge=0, le=12)
    data: dict[str, Any] = Field(default_factory=dict)


# ----------------------------- billing -----------------------------
class CheckoutRequest(BaseModel):
    plan_code: Literal["basic", "pro", "elite"]


class MockCompleteRequest(BaseModel):
    checkout_token: str


class ChangePlanRequest(BaseModel):
    plan_code: Literal["free", "basic", "pro", "elite"]


class CancelSubscriptionRequest(BaseModel):
    immediate: bool = False


class ConsentRequest(BaseModel):
    accepted: bool


class RefundRequest(BaseModel):
    payment_id: str
    amount: float = Field(gt=0)
    reason: str = Field(min_length=3, max_length=400)


class PlanUpdateRequest(BaseModel):
    price_monthly: float | None = Field(default=None, ge=0, le=10000)
    is_active: bool | None = None
    features: list[str] | None = None
    limits: dict[str, Any] | None = None
    tagline: str | None = Field(default=None, max_length=200)


# ----------------------------- connections -----------------------------
class ConnectionCreateRequest(BaseModel):
    provider: str
    label: str = Field(min_length=2, max_length=80)
    environment: Literal["read_only", "paper", "live"] = "read_only"
    api_key: str = Field(default="", max_length=400)
    api_secret: str = Field(default="", max_length=400)
    passphrase: str = Field(default="", max_length=400)
    account_id: str = Field(default="", max_length=200)
    # Deriv requires its own App ID header for API-token (PAT) authentication.
    app_id: str = Field(default="", max_length=64)
    withdrawal_attestation: bool = False


class ConnectionRotateRequest(BaseModel):
    api_key: str = Field(min_length=4, max_length=400)
    api_secret: str = Field(default="", max_length=400)
    passphrase: str = Field(default="", max_length=400)
    account_id: str = Field(default="", max_length=200)
    app_id: str = Field(default="", max_length=64)


# ----------------------------- trading -----------------------------
class OrderCreateRequest(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)
    order_type: Literal["market", "limit", "stop", "stop_limit"] = "market"
    price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    mode: Literal["paper", "live"] = "paper"
    connection_id: str | None = None
    paper_session_id: str | None = None
    strategy_version_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=120)
    reason: str = Field(default="Manual order from trading terminal", max_length=500)


class ClosePositionRequest(BaseModel):
    reason: str = Field(default="Manual close requested", max_length=300)
    note: str | None = Field(default=None, max_length=500)


class KillSwitchRequest(BaseModel):
    scope: Literal["org", "provider", "user"] = "org"
    target: str | None = None
    reason: str = Field(min_length=3, max_length=400)
    flatten: bool = False


class LiveAuthorizationStart(BaseModel):
    acknowledged: bool
    checklist: dict[str, bool]
    totp_code: str | None = None
    jurisdiction: str = Field(min_length=2, max_length=2)
    connection_id: str | None = None


class LiveAuthorizationConfirm(BaseModel):
    confirmation_token: str
    reason: str = Field(default="User confirmed live trading authorisation", max_length=300)


# ----------------------------- strategies -----------------------------
class BacktestRequest(BaseModel):
    strategy_code: str
    symbol: str
    timeframe: Literal["15m", "1h", "4h", "1d"] = "1h"
    params: dict[str, Any] = Field(default_factory=dict)
    start: datetime | None = None
    end: datetime | None = None
    walk_forward: bool = False


class StrategyVersionRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    changelog: str = Field(default="", max_length=2000)


class StrategyApproveRequest(BaseModel):
    acknowledge_risk: bool


class PaperSessionRequest(BaseModel):
    strategy_code: str
    symbol: str = "BTC/USDT"
    timeframe: Literal["15m", "1h", "4h", "1d"] = "1h"
    params: dict[str, Any] = Field(default_factory=dict)


# ----------------------------- admin -----------------------------
class RiskPolicyUpdate(BaseModel):
    rules: dict[str, Any]
    reason: str = Field(min_length=3, max_length=400)


class FeatureFlagUpdate(BaseModel):
    enabled: bool
    description: str | None = None
    rollout: dict[str, Any] | None = None


class EntitlementOverrideRequest(BaseModel):
    org_id: str
    key: str
    value: Any
    reason: str = Field(min_length=3, max_length=400)
    expires_at: datetime | None = None


class CostModelUpdate(BaseModel):
    infra_monthly_usd: float = Field(ge=0)
    ai_monthly_usd: float = Field(ge=0)
    support_cost_per_ticket_usd: float = Field(ge=0)
    notes: str = Field(default="", max_length=500)


class PerformanceFeeSettings(BaseModel):
    enabled: bool
    rate: float = Field(ge=0, le=0.5)
    legal_review_completed: bool
    jurisdictions_allowed: list[str] = Field(default_factory=list)


class PerformanceFeeComputeRequest(BaseModel):
    org_id: str
    period_start: datetime
    period_end: datetime


class UserAdminUpdate(BaseModel):
    status: Literal["active", "suspended", "pending"] | None = None
    staff_role: Literal["owner", "admin", "support", "analyst"] | None = None
    is_staff: bool | None = None
    reason: str = Field(default="", max_length=400)


class TicketReply(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    status: Literal["open", "pending", "resolved"] | None = None


class SupportTicketCreate(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=5, max_length=4000)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"


# ------------------------- binary contracts -------------------------
class BinaryQuoteRequest(BaseModel):
    symbol: str = Field(min_length=3, max_length=48)
    duration_seconds: int = Field(gt=0, le=86_400)


class BinaryContractRequest(BaseModel):
    symbol: str = Field(min_length=3, max_length=48)
    direction: Literal["call", "put"]
    stake: float = Field(gt=0, le=100_000)
    duration_seconds: int = Field(gt=0, le=86_400)
    idempotency_key: str | None = Field(default=None, max_length=120)
    reason: str = Field(default="Manual contract from terminal", max_length=400)


class CopilotAnalyseRequest(BaseModel):
    symbol: str = Field(min_length=3, max_length=48)
    timeframe: Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d"] = "15m"
    duration_seconds: int | None = Field(default=None, gt=0, le=86_400)
