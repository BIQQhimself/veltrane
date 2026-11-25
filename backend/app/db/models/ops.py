from __future__ import annotations

from datetime import datetime

from app.db.base import Base, IdTimestampMixin, TimestampMixin, new_id
from app.db.types import JSONType, MoneyType
from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column


class Notification(Base, IdTimestampMixin):
    __tablename__ = "notifications"

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), nullable=False, index=True
    )
    user_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), index=True)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailOutbox(Base, IdTimestampMixin):
    __tablename__ = "email_outbox"

    to_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(240), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="system", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(160))
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupportTicket(Base, IdTimestampMixin):
    __tablename__ = "support_tickets"

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)
    messages: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    org_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), index=True)
    actor_email: Mapped[str | None] = mapped_column(String(320))
    actor_role: Mapped[str | None] = mapped_column(String(24))
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(48))
    target_id: Mapped[str | None] = mapped_column(String(80))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    meta: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FeatureFlag(Base, TimestampMixin):
    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    rollout: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))


class UsageMetric(Base, IdTimestampMixin):
    __tablename__ = "usage_metrics"
    __table_args__ = (UniqueConstraint("org_id", "metric", "period", name="uq_usage_org_metric_period"),)

    org_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    metric: Mapped[str] = mapped_column(String(48), nullable=False)
    period: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    meta: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


class AiUsage(Base, IdTimestampMixin):
    __tablename__ = "ai_usage"

    org_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(48), nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)


class SystemSetting(Base, TimestampMixin):
    """Key/value store for admin-editable configuration (never secrets)."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    description: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    updated_by: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
