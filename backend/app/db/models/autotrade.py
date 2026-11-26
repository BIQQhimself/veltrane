from __future__ import annotations

from datetime import datetime

from app.db.base import Base, IdTimestampMixin
from app.db.types import JSONType, MoneyType
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column


class AutoTradeConfig(Base, IdTimestampMixin):
    """Per-connection automation settings.

    ``mode`` is either ``approval`` (every entry waits for a human) or ``autonomous`` (the runner
    submits through the risk engine without asking). Both are subordinate to the platform live
    switch, the connection's live permission and the subscriber's explicit authorisation.
    """

    __tablename__ = "auto_trade_configs"
    __table_args__ = (UniqueConstraint("connection_id", name="uq_auto_trade_connection"),)

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default="approval", nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), default="R_100", nullable=False)
    contract_type: Mapped[str] = mapped_column(String(24), default="CALL", nullable=False)
    stake: Mapped[float] = mapped_column(MoneyType, default=10.0, nullable=False)
    duration: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    duration_unit: Mapped[str] = mapped_column(String(4), default="t", nullable=False)
    max_open_contracts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_stake_per_trade: Mapped[float] = mapped_column(MoneyType, default=25.0, nullable=False)
    daily_loss_limit: Mapped[float] = mapped_column(MoneyType, default=100.0, nullable=False)
    daily_stake_limit: Mapped[float] = mapped_column(MoneyType, default=250.0, nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    signal_ttl_seconds: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    created_by: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_signal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    halt_reason: Mapped[str | None] = mapped_column(Text)


class AutoTradeSignal(Base, IdTimestampMixin):
    """One proposed entry. Approved signals become orders; nothing here moves money."""

    __tablename__ = "auto_trade_signals"

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    config_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("auto_trade_configs.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(16), default="approval", nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    contract_type: Mapped[str] = mapped_column(String(24), nullable=False)
    stake: Mapped[float] = mapped_column(MoneyType, nullable=False)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_unit: Mapped[str] = mapped_column(String(4), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    risk_snapshot: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    order_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("orders.id", ondelete="SET NULL"))
    contract_id: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"))
