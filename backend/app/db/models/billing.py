from __future__ import annotations

from datetime import datetime

from app.db.base import Base, IdTimestampMixin, TimestampMixin
from app.db.types import JSONType, MoneyType
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column


class Plan(Base, TimestampMixin):
    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    tagline: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    price_monthly: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    features: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    limits: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    trial_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Subscription(Base, IdTimestampMixin):
    __tablename__ = "subscriptions"

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_code: Mapped[str] = mapped_column(String(32), ForeignKey("plans.code"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="mock", nullable=False)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(120), index=True)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seats: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    pending_plan_code: Mapped[str | None] = mapped_column(String(32))
    pending_effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EntitlementOverride(Base, IdTimestampMixin):
    __tablename__ = "entitlement_overrides"

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[dict] = mapped_column(JSONType, nullable=False)
    reason: Mapped[str] = mapped_column(String(400), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"))


class Payment(Base, IdTimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("provider", "provider_payment_id", name="uq_payments_provider_payment"),)

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_payment_id: Mapped[str] = mapped_column(String(160), nullable=False)
    provider_invoice_id: Mapped[str | None] = mapped_column(String(160))
    amount: Mapped[float] = mapped_column(MoneyType, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    receipt_url: Mapped[str | None] = mapped_column(String(500))
    refunded_amount: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    raw: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


class Invoice(Base, IdTimestampMixin):
    __tablename__ = "invoices"

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    subtotal: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    tax: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    total: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_invoice_id: Mapped[str | None] = mapped_column(String(160))
    line_items: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)


class Refund(Base, IdTimestampMixin):
    __tablename__ = "refunds"

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("payments.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[float] = mapped_column(MoneyType, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    reason: Mapped[str] = mapped_column(String(400), nullable=False)
    provider_refund_id: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"))


class WebhookEvent(Base, IdTimestampMixin):
    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),)

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="received", nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class PerformanceFeeRecord(Base, IdTimestampMixin):
    __tablename__ = "performance_fee_records"

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    realized_pnl: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    hwm_before: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    hwm_after: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    fee_rate: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    fee_amount: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    consent_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("fee_consents.id"))
    calculation: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class HighWaterMark(Base, IdTimestampMixin):
    __tablename__ = "high_water_marks"
    __table_args__ = (UniqueConstraint("org_id", "scope", "strategy_version_id", name="uq_hwm_org_scope_strategy"),)

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope: Mapped[str] = mapped_column(String(24), default="org", nullable=False)
    strategy_version_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    value: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FeeConsent(Base, IdTimestampMixin):
    __tablename__ = "fee_consents"

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), nullable=False)
    document_version: Mapped[str] = mapped_column(String(24), nullable=False)
    fee_rate: Mapped[float] = mapped_column(MoneyType, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
