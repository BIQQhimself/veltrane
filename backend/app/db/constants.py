"""Domain constants shared by services, API schemas and tests."""

from __future__ import annotations

_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


class TradingRule:
    """Platform rules that every execution path must satisfy.

    The one-minute floor is a product decision, not a venue capability: Deriv will happily
    price 1-tick and 15-second contracts, and the platform still refuses them. Keeping the
    number here means the paper book, the venue adapter, the API schemas and the agent all
    read the same constant instead of each carrying its own copy.
    """

    MIN_DURATION_SECONDS = 60

    @classmethod
    def term_seconds(cls, value: int, unit: str) -> int | None:
        """Wall-clock seconds for a ``<value><unit>`` term, or ``None`` for ticks."""
        multiplier = _UNIT_SECONDS.get(unit)
        return value * multiplier if multiplier else None

    @classmethod
    def below_floor(cls, value: int, unit: str) -> bool:
        seconds = cls.term_seconds(value, unit)
        return seconds is None or seconds < cls.MIN_DURATION_SECONDS


class PlanCode:
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ELITE = "elite"
    VIP = "vip"
    ALL = (FREE, BASIC, PRO, ELITE, VIP)


class SubscriptionStatus:
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"


class UserStatus:
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class StaffRole:
    OWNER = "owner"
    ADMIN = "admin"
    SUPPORT = "support"
    ANALYST = "analyst"
    ALL = (OWNER, ADMIN, SUPPORT, ANALYST)


class OrderSide:
    BUY = "buy"
    SELL = "sell"


class OrderStatus:
    INTENT = "intent"
    REJECTED = "rejected"
    SUBMITTED = "submitted"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    FAILED = "failed"


class OrderType:
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TradeMode:
    PAPER = "paper"
    LIVE = "live"


class ConnectionEnvironment:
    READ_ONLY = "read_only"
    PAPER = "paper"
    LIVE = "live"


class ConnectionStatus:
    PENDING = "pending"
    CONNECTED = "connected"
    ERROR = "error"
    REVOKED = "revoked"


class KillScope:
    GLOBAL = "global"
    ORG = "org"
    PROVIDER = "provider"
    USER = "user"


class StrategyStatus:
    DRAFT = "draft"
    APPROVED = "approved"
    LIVE = "live"
    RETIRED = "retired"


class NotificationCategory:
    TRADE = "trade"
    ORDER = "order"
    RISK = "risk"
    CONNECTION = "connection"
    BILLING = "billing"
    SECURITY = "security"
    SYSTEM = "system"


class Severity:
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    CRITICAL = "critical"


class FeeKind:
    TRADING = "trading"
    FUNDING = "funding"
    PERFORMANCE = "performance"
    SUBSCRIPTION = "subscription"


class AuditAction:
    USER_REGISTERED = "user.registered"
    USER_LOGIN = "user.login"
    USER_LOGIN_FAILED = "user.login_failed"
    USER_LOGOUT = "user.logout"
    MFA_ENABLED = "mfa.enabled"
    MFA_DISABLED = "mfa.disabled"
    PASSWORD_CHANGED = "password.changed"
    SUBSCRIPTION_CHANGED = "subscription.changed"
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_FAILED = "payment.failed"
    REFUND_ISSUED = "refund.issued"
    CONNECTION_CREATED = "connection.created"
    CONNECTION_RECONNECTED = "connection.reconnected"
    CONNECTION_REVOKED = "connection.revoked"
    CONNECTION_SYNCED = "connection.synced"
    CREDENTIAL_ROTATED = "credential.rotated"
    ORDER_INTENT = "order.intent"
    ORDER_APPROVED = "order.approved"
    ORDER_REJECTED = "order.rejected"
    ORDER_SUBMITTED = "order.submitted"
    ORDER_FILLED = "order.filled"
    ORDER_FAILED = "order.failed"
    ORDER_CANCELLED = "order.cancelled"
    TRADE_CLOSED = "trade.closed"
    POSITION_CLOSED = "position.closed"
    RISK_POLICY_UPDATED = "risk.policy_updated"
    KILL_SWITCH_ENGAGED = "kill_switch.engaged"
    KILL_SWITCH_RELEASED = "kill_switch.released"
    LIVE_AUTH_REQUESTED = "live.authorization_requested"
    LIVE_AUTH_GRANTED = "live.authorization_granted"
    LIVE_AUTH_REVOKED = "live.authorization_revoked"
    STRATEGY_VERSION_APPROVED = "strategy.version_approved"
    ADMIN_ACTION = "admin.action"
    LIVE_SWITCH_CHANGED = "admin.live_trading_switch"
    FEATURE_FLAG_CHANGED = "feature_flag.changed"
    AUTOTRADE_UPDATED = "autotrade.updated"
    BACKTEST_COMPLETED = "backtest.completed"


class Entitlement:
    """Named capabilities unlocked by plans. Limits are numeric, features boolean."""

    MAX_CONNECTIONS = "max_connections"
    MAX_OPEN_POSITIONS = "max_open_positions"
    MAX_DAILY_DEMO_EXECUTIONS = "max_daily_demo_executions"
    STRATEGY_LIBRARY = "strategy_library"
    BACKTESTING = "backtesting"
    STRATEGY_CUSTOMIZATION = "strategy_customization"
    ADVANCED_ANALYTICS = "advanced_analytics"
    AUTOMATION = "automation"
    AUTOMATION_MODE = "automation_mode"
    MAX_AUTOMATED_TRADES_PER_DAY = "max_automated_trades_per_day"
    PORTFOLIO_OPTIMIZATION = "portfolio_optimization"
    PRIORITY_SUPPORT = "priority_support"
    PERFORMANCE_FEES = "performance_fees"
    LIVE_TRADING = "live_trading"
    MAX_BACKTESTS_PER_DAY = "max_backtests_per_day"
    API_ACCESS = "api_access"
