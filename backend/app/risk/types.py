from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Side = Literal["buy", "sell"]
Mode = Literal["paper", "live"]


@dataclass(frozen=True)
class OrderIntent:
    org_id: str
    mode: Mode
    symbol: str
    side: Side
    quantity: float
    order_type: str = "market"
    price: float | None = None
    stop_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    strategy_version_id: str | None = None
    strategy_status: str | None = None
    client_order_id: str = ""
    idempotency_key: str = ""
    reason: str = ""
    source: str = "ai_strategy"
    reduce_only: bool = False

    def as_dict(self) -> dict:
        return {
            "org_id": self.org_id,
            "mode": self.mode,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "price": self.price,
            "stop_price": self.stop_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "strategy_version_id": self.strategy_version_id,
            "strategy_status": self.strategy_status,
            "client_order_id": self.client_order_id,
            "idempotency_key": self.idempotency_key,
            "reason": self.reason,
            "source": self.source,
            "reduce_only": self.reduce_only,
        }


@dataclass(frozen=True)
class PositionView:
    symbol: str
    side: str
    quantity: float
    notional: float
    unrealized_pnl: float = 0.0
    stop_loss: float | None = None


@dataclass(frozen=True)
class InstrumentView:
    symbol: str
    asset_class: str
    min_qty: float = 0.0
    qty_step: float = 0.0
    tick_size: float = 0.0
    max_leverage: float = 1.0
    is_active: bool = True


@dataclass(frozen=True)
class MarketView:
    price: float
    bid: float | None = None
    ask: float | None = None
    as_of: datetime | None = None
    age_seconds: float | None = None
    spread_bps: float | None = None
    source: str = "unknown"


@dataclass(frozen=True)
class RiskContext:
    """Everything the risk engine is allowed to know.

    The engine imports nothing from strategies or the execution layer: a caller must
    assemble this plain data structure. That is what makes an AI bypass impossible.
    """

    now: datetime
    mode: Mode
    policy: dict
    policy_id: str | None = None
    policy_version: int = 1

    global_live_enabled: bool = False
    org_live_authorized: bool = False
    org_live_entitlement: bool = False
    org_suspended: bool = False

    kill_global: bool = False
    kill_org: bool = False
    kill_provider: bool = False
    kill_user: bool = False

    connection_trade_permission: bool = False
    connection_read_only: bool = True
    # True when the venue account is the venue's own demo account: no real funds move, so the
    # platform live flag and the subscriber's live authorisation do not apply. Kill switches,
    # connection permission and every other rule still do.
    venue_demo: bool = False

    equity: float = 0.0
    cash: float = 0.0
    peak_equity: float = 0.0
    realized_pnl_today: float = 0.0
    unrealized_pnl: float = 0.0
    consecutive_losses: int = 0
    # When the most recent loss closed. The consecutive-loss breaker lifts after a cool-down
    # instead of waiting for a win that the block itself prevents.
    last_loss_at: datetime | None = None

    positions: list[PositionView] = field(default_factory=list)
    account_exposure: float = 0.0
    portfolio_exposure: float = 0.0
    open_position_count: int = 0

    instrument: InstrumentView = field(default_factory=lambda: InstrumentView(symbol="", asset_class="crypto"))
    market: MarketView = field(default_factory=lambda: MarketView(price=0.0))

    duplicate_exists: bool = False
    executions_today: int = 0
    # Real-money executions placed today. Counted separately from demo ones so the plan's
    # daily allowance covers both environments instead of only simulated trading.
    live_executions_today: int = 0
    daily_execution_limit: int | None = None
    market_open: bool = True
    is_demo_feed: bool = False

    def with_extra(self, **kwargs) -> RiskContext:
        data = {**self.__dict__, **kwargs}
        return RiskContext(**data)


@dataclass(frozen=True)
class RuleResult:
    code: str
    passed: bool
    message: str
    severity: str = "blocking"
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "passed": self.passed,
            "message": self.message,
            "severity": self.severity,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class RiskAssessment:
    approved: bool
    checks: list[RuleResult]
    policy_id: str | None
    policy_version: int
    intent: OrderIntent
    notional: float
    reference_price: float

    @property
    def failed(self) -> list[RuleResult]:
        return [c for c in self.checks if not c.passed]

    @property
    def failed_codes(self) -> list[str]:
        return [c.code for c in self.failed]

    def as_dict(self) -> dict:
        return {
            "approved": self.approved,
            "decision": "approved" if self.approved else "rejected",
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "notional": self.notional,
            "reference_price": self.reference_price,
            "failed_rules": [c.as_dict() for c in self.failed],
            "checks": [c.as_dict() for c in self.checks],
            "intent": self.intent.as_dict(),
        }


DEFAULT_RISK_RULES: dict = {
    "max_position_notional_pct": 10.0,
    "max_account_exposure_pct": 30.0,
    "max_portfolio_exposure_pct": 50.0,
    "max_leverage": 3.0,
    "daily_loss_limit_pct": 3.0,
    "max_drawdown_pct": 15.0,
    "max_open_positions": 5,
    "max_price_age_seconds": 30,
    "max_spread_bps": 50,
    "max_stop_distance_pct": 12.0,
    "require_stop_loss_live": True,
    "max_order_notional_abs": 100_000,
    "min_notional": 10,
    "max_consecutive_losses": 4,
    "circuit_breaker_cooldown_minutes": 60,
    "allow_short": True,
    "limit_price_band_pct": 5.0,
}


def merged_rules(policy_rules: dict | None) -> dict:
    rules = dict(DEFAULT_RISK_RULES)
    if policy_rules:
        rules.update({k: v for k, v in policy_rules.items() if v is not None})
    return rules
