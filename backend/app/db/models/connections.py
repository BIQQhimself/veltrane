from __future__ import annotations

from datetime import datetime

from app.db.base import Base, IdTimestampMixin
from app.db.types import JSONType, MoneyType, QtyType
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column


class Connection(Base, IdTimestampMixin):
    __tablename__ = "connections"
    __table_args__ = (UniqueConstraint("org_id", "label", name="uq_connections_org_label"),)

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # exchange | broker
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # binance | bybit | okx | deriv | paper
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    environment: Mapped[str] = mapped_column(String(16), default="read_only", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    permissions: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    capabilities: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    is_sandbox: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Venue identity, as reported by the provider. Never credential material.
    provider_account_id: Mapped[str | None] = mapped_column(String(64))
    provider_account_type: Mapped[str | None] = mapped_column(String(16))  # demo | real
    provider_currency: Mapped[str | None] = mapped_column(String(16))
    provider_meta: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    session_state: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    last_auth_error: Mapped[str | None] = mapped_column(Text)
    last_auth_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConnectionCredential(Base, IdTimestampMixin):
    """Envelope-encrypted provider secrets. Never serialised to any API response."""

    __tablename__ = "connection_credentials"

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("connections.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    envelope: Mapped[str] = mapped_column(Text, nullable=False)
    kek_version: Mapped[int] = mapped_column(nullable=False, default=1)
    key_hint: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Balance(Base, IdTimestampMixin):
    __tablename__ = "balances"
    __table_args__ = (UniqueConstraint("connection_id", "asset", name="uq_balances_connection_asset"),)

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset: Mapped[str] = mapped_column(String(24), nullable=False)
    free: Mapped[float] = mapped_column(QtyType, default=0, nullable=False)
    locked: Mapped[float] = mapped_column(QtyType, default=0, nullable=False)
    total: Mapped[float] = mapped_column(QtyType, default=0, nullable=False)
    usd_value: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LedgerTransaction(Base, IdTimestampMixin):
    __tablename__ = "ledger_transactions"

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("connections.id", ondelete="SET NULL"), index=True
    )
    type: Mapped[str] = mapped_column(String(24), nullable=False)
    asset: Mapped[str] = mapped_column(String(24), nullable=False)
    amount: Mapped[float] = mapped_column(MoneyType, nullable=False)
    fee: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(32))
    reference_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    external_id: Mapped[str | None] = mapped_column(String(160))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    meta: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


class ProviderAuthEvent(Base, IdTimestampMixin):
    """Authentication and session events for provider connections.

    Admins need to see failed Deriv authentications without reading subscriber secrets; nothing
    here stores a token, only the outcome and Deriv's own error code.
    """

    __tablename__ = "provider_auth_events"

    org_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    connection_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("connections.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)  # ok | failed
    code: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
