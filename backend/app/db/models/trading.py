from __future__ import annotations

from datetime import datetime

from app.db.base import Base, IdTimestampMixin, TimestampMixin
from app.db.types import JSONType, MoneyType, QtyType
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column


class Instrument(Base, TimestampMixin):
    __tablename__ = "instruments"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    asset_class: Mapped[str] = mapped_column(String(24), nullable=False)
    venue: Mapped[str] = mapped_column(String(32), default="generic", nullable=False)
    base: Mapped[str] = mapped_column(String(24), nullable=False)
    quote: Mapped[str] = mapped_column(String(24), nullable=False)
    tick_size: Mapped[float] = mapped_column(MoneyType, default=0.00000001, nullable=False)
    min_qty: Mapped[float] = mapped_column(QtyType, default=0, nullable=False)
    contract_size: Mapped[float] = mapped_column(MoneyType, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Strategy(Base, IdTimestampMixin):
    __tablename__ = "strategies"

    org_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"))


class StrategyVersion(Base, IdTimestampMixin):
    __tablename__ = "strategy_versions"
    __table_args__ = (UniqueConstraint("strategy_id", "version", name="uq_strategy_version"),)

    strategy_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    supported_markets: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    timeframes: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    params_schema: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    default_params: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    entry_rules: Mapped[str] = mapped_column(Text, default="", nullable=False)
    exit_rules: Mapped[str] = mapped_column(Text, default="", nullable=False)
    risk_params: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    data_requirements: Mapped[str] = mapped_column(Text, default="", nullable=False)
    backtest_methodology: Mapped[str] = mapped_column(Text, default="", nullable=False)
    known_limitations: Mapped[str] = mapped_column(Text, default="", nullable=False)
    changelog: Mapped[str] = mapped_column(Text, default="", nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Backtest(Base, IdTimestampMixin):
    __tablename__ = "backtests"

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    strategy_version_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("strategy_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_symbol: Mapped[str] = mapped_column(String(48), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    params: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    cost_model: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    equity_curve: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    trades_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    data_source: Mapped[str] = mapped_column(String(24), default="unknown", nullable=False)
    engine_version: Mapped[str] = mapped_column(String(24), default="1.0.0", nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaperSession(Base, IdTimestampMixin):
    __tablename__ = "paper_sessions"

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    strategy_version_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("strategy_versions.id"))
    connection_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("connections.id", ondelete="SET NULL")
    )
    instrument_symbol: Mapped[str] = mapped_column(String(48), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), default="1h", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False)
    starting_balance: Mapped[float] = mapped_column(MoneyType, default=25000, nullable=False)
    cash_balance: Mapped[float] = mapped_column(MoneyType, default=25000, nullable=False)
    equity: Mapped[float] = mapped_column(MoneyType, default=25000, nullable=False)
    config: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    last_tick_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Position(Base, IdTimestampMixin):
    __tablename__ = "positions"

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mode: Mapped[str] = mapped_column(String(8), default="paper", nullable=False)
    connection_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("connections.id", ondelete="SET NULL"), index=True
    )
    paper_session_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("paper_sessions.id", ondelete="CASCADE"), index=True
    )
    instrument_symbol: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[float] = mapped_column(QtyType, nullable=False)
    avg_entry_price: Mapped[float] = mapped_column(MoneyType, nullable=False)
    mark_price: Mapped[float] = mapped_column(MoneyType, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    leverage: Mapped[float] = mapped_column(MoneyType, default=1, nullable=False)
    stop_loss: Mapped[float | None] = mapped_column(MoneyType)
    take_profit: Mapped[float | None] = mapped_column(MoneyType)
    strategy_version_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("strategy_versions.id"))
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Order(Base, IdTimestampMixin):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("org_id", "client_order_id", name="uq_orders_org_client"),
        UniqueConstraint("org_id", "idempotency_key", name="uq_orders_org_idempotency"),
    )

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mode: Mapped[str] = mapped_column(String(8), default="paper", nullable=False)
    connection_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("connections.id", ondelete="SET NULL")
    )
    paper_session_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("paper_sessions.id", ondelete="SET NULL"), index=True
    )
    instrument_symbol: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), default="market", nullable=False)
    quantity: Mapped[float] = mapped_column(QtyType, nullable=False)
    price: Mapped[float | None] = mapped_column(MoneyType)
    stop_price: Mapped[float | None] = mapped_column(MoneyType)
    time_in_force: Mapped[str] = mapped_column(String(8), default="gtc", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="intent", nullable=False)
    client_order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    strategy_version_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("strategy_versions.id"))
    risk_decision_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    filled_qty: Mapped[float] = mapped_column(QtyType, default=0, nullable=False)
    avg_fill_price: Mapped[float | None] = mapped_column(MoneyType)
    fee: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    fee_currency: Mapped[str] = mapped_column(String(16), default="USDT", nullable=False)
    slippage_est_bps: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    slippage_actual_bps: Mapped[float | None] = mapped_column(MoneyType)
    provider_order_id: Mapped[str | None] = mapped_column(String(160))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Venue-specific contract facts (contract id, payout, duration, quote) for the detail view.
    meta: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


class Trade(Base, IdTimestampMixin):
    __tablename__ = "trades"

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("orders.id", ondelete="SET NULL"), index=True
    )
    position_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("positions.id", ondelete="SET NULL")
    )
    paper_session_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("paper_sessions.id", ondelete="SET NULL"), index=True
    )
    mode: Mapped[str] = mapped_column(String(8), default="paper", nullable=False)
    instrument_symbol: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[float] = mapped_column(QtyType, nullable=False)
    entry_price: Mapped[float] = mapped_column(MoneyType, nullable=False)
    exit_price: Mapped[float] = mapped_column(MoneyType, nullable=False)
    notional: Mapped[float] = mapped_column(MoneyType, nullable=False)
    fees: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    funding: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    slippage_est_bps: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    slippage_actual_bps: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    gross_pnl: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    net_pnl: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    entry_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    exit_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    strategy_version_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("strategy_versions.id"))
    risk_snapshot: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    human_intervention: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    intervention_note: Mapped[str | None] = mapped_column(Text)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Fee(Base, IdTimestampMixin):
    __tablename__ = "fees"

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    amount: Mapped[float] = mapped_column(MoneyType, nullable=False)
    currency: Mapped[str] = mapped_column(String(16), default="USD", nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(32))
    reference_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    detail: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RiskPolicy(Base, IdTimestampMixin):
    __tablename__ = "risk_policies"

    org_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80), default="default", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    rules: Mapped[dict] = mapped_column(JSONType, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"))


class RiskDecision(Base, IdTimestampMixin):
    __tablename__ = "risk_decisions"

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_intent: Mapped[dict] = mapped_column(JSONType, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    failed_rules: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    checks: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    policy_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    policy_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    order_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


class TradingPermission(Base, IdTimestampMixin):
    __tablename__ = "trading_permissions"

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), nullable=False)
    live_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    authorization_method: Mapped[str | None] = mapped_column(String(40))
    checklist: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    risk_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirm_token_hash: Mapped[str | None] = mapped_column(String(64))
    confirm_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(400))
    jurisdiction: Mapped[str | None] = mapped_column(String(2))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))


class KillSwitch(Base, IdTimestampMixin):
    __tablename__ = "kill_switches"
    __table_args__ = (UniqueConstraint("scope", "target", name="uq_kill_scope_target"),)

    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    target: Mapped[str] = mapped_column(String(80), nullable=False)
    engaged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(400))
    engaged_by: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"))
    engaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BinaryContract(Base, IdTimestampMixin):
    """A fixed-odds binary contract (paper only in this build).

    The stake is debited at open and the payout credited at settlement, so cash
    accounting matches the economic risk. ``status`` is open | won | lost | void |
    rejected. Rejected rows exist for audit parity with orders.
    """

    __tablename__ = "binary_contracts"
    __table_args__ = (UniqueConstraint("org_id", "idempotency_key", name="uq_binary_org_idempotency"),)

    org_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_session_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("paper_sessions.id", ondelete="SET NULL"), index=True
    )
    mode: Mapped[str] = mapped_column(String(8), default="paper", nullable=False)
    instrument_symbol: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    asset_class: Mapped[str] = mapped_column(String(24), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    stake: Mapped[float] = mapped_column(MoneyType, nullable=False)
    payout_pct: Mapped[float] = mapped_column(MoneyType, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_price: Mapped[float] = mapped_column(MoneyType, nullable=False)
    exit_price: Mapped[float | None] = mapped_column(MoneyType)
    price_source: Mapped[str] = mapped_column(String(24), default="demo", nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)
    net_pnl: Mapped[float] = mapped_column(MoneyType, default=0, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    risk_decision_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    trade_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("trades.id", ondelete="SET NULL"), index=True
    )
    strategy_version_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("strategy_versions.id"))
    source: Mapped[str] = mapped_column(String(24), default="human", nullable=False)
    entry_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    risk_snapshot: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
