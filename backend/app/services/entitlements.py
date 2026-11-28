from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.errors import forbidden
from app.db.constants import Entitlement, NotificationCategory, PlanCode, Severity, SubscriptionStatus
from app.db.models import EntitlementOverride, Notification, Plan, Subscription
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Plan catalogue. Limits are the only server-side authority for capabilities.
# 0 means "no numeric cap"; booleans gate features outright.
# ---------------------------------------------------------------------------
PLAN_CATALOG: list[dict] = [
    {
        "code": PlanCode.FREE,
        "name": "Free",
        "tagline": "Connect, observe and analyse. No trade execution.",
        "price_monthly": 0,
        "sort_order": 0,
        "trial_days": 0,
        "features": [
            "Read-only exchange & broker connections",
            "Portfolio analytics",
            "Market monitoring",
            "No trade execution — connect and observe only",
            "No automated trading",
        ],
        "limits": {
            Entitlement.MAX_CONNECTIONS: 2,
            Entitlement.MAX_OPEN_POSITIONS: 3,
            Entitlement.MAX_DAILY_EXECUTIONS: 0,
            Entitlement.MAX_BACKTESTS_PER_DAY: 0,
            Entitlement.STRATEGY_LIBRARY: ["trend_following_v1"],
            Entitlement.BACKTESTING: False,
            Entitlement.STRATEGY_CUSTOMIZATION: False,
            Entitlement.ADVANCED_ANALYTICS: False,
            Entitlement.AUTOMATION: False,
            Entitlement.AUTOMATION_MODE: "none",
            Entitlement.MAX_AUTOMATED_TRADES_PER_DAY: 0,
            Entitlement.PORTFOLIO_OPTIMIZATION: False,
            Entitlement.PRIORITY_SUPPORT: False,
            Entitlement.PERFORMANCE_FEES: False,
            Entitlement.LIVE_TRADING: False,
            Entitlement.API_ACCESS: False,
        },
    },
    {
        "code": PlanCode.BASIC,
        "name": "Basic",
        "tagline": "Live trading and an autonomous agent that works while the platform is open.",
        "price_monthly": 19,
        "sort_order": 1,
        "trial_days": 7,
        "features": [
            "Core AI strategy library",
            "Manual trading, demo or live after authorisation",
            "Autonomous agent while the platform is open (session mode)",
            "600 trades per day",
            "Essential analytics",
        ],
        "limits": {
            Entitlement.MAX_CONNECTIONS: 3,
            Entitlement.MAX_OPEN_POSITIONS: 5,
            Entitlement.MAX_DAILY_EXECUTIONS: 600,
            Entitlement.MAX_BACKTESTS_PER_DAY: 0,
            Entitlement.STRATEGY_LIBRARY: ["trend_following_v1", "mean_reversion_v1"],
            Entitlement.BACKTESTING: False,
            Entitlement.STRATEGY_CUSTOMIZATION: False,
            Entitlement.ADVANCED_ANALYTICS: False,
            Entitlement.AUTOMATION: True,
            Entitlement.AUTOMATION_MODE: "session",
            Entitlement.MAX_AUTOMATED_TRADES_PER_DAY: 600,
            Entitlement.PORTFOLIO_OPTIMIZATION: False,
            Entitlement.PRIORITY_SUPPORT: False,
            Entitlement.PERFORMANCE_FEES: False,
            Entitlement.LIVE_TRADING: True,
            Entitlement.API_ACCESS: False,
        },
    },
    {
        "code": PlanCode.PRO,
        "name": "Pro",
        "tagline": "The agent keeps trading when you close the platform.",
        "price_monthly": 49,
        "sort_order": 2,
        "trial_days": 7,
        "features": [
            "Expanded strategy library",
            "Backtesting & walk-forward testing",
            "Strategy customisation",
            "Advanced analytics",
            "Autonomous trading that continues when you close the platform",
            "1,200 trades per day",
            "Eligible for live trading after explicit authorisation",
        ],
        "limits": {
            Entitlement.MAX_CONNECTIONS: 8,
            Entitlement.MAX_OPEN_POSITIONS: 15,
            Entitlement.MAX_DAILY_EXECUTIONS: 1200,
            Entitlement.MAX_BACKTESTS_PER_DAY: 25,
            Entitlement.STRATEGY_LIBRARY: ["trend_following_v1", "mean_reversion_v1", "breakout_v1"],
            Entitlement.BACKTESTING: True,
            Entitlement.STRATEGY_CUSTOMIZATION: True,
            Entitlement.ADVANCED_ANALYTICS: True,
            Entitlement.AUTOMATION: True,
            Entitlement.AUTOMATION_MODE: "background",
            Entitlement.MAX_AUTOMATED_TRADES_PER_DAY: 1200,
            Entitlement.PORTFOLIO_OPTIMIZATION: False,
            Entitlement.PRIORITY_SUPPORT: False,
            Entitlement.PERFORMANCE_FEES: False,
            Entitlement.LIVE_TRADING: True,
            Entitlement.API_ACCESS: True,
        },
    },
    {
        "code": PlanCode.ELITE,
        "name": "Elite",
        "tagline": "Full library, portfolio optimisation and the highest configurable limits.",
        "price_monthly": 149,
        "sort_order": 3,
        "trial_days": 7,
        "features": [
            "Full eligible strategy library",
            "Advanced AI customisation",
            "Portfolio optimisation",
            "Background autonomous trading, 2,400 trades per day",
            "High configurable trading limits",
            "Priority support",
            "Optional performance fee agreement (requires separate consent)",
        ],
        "limits": {
            Entitlement.MAX_CONNECTIONS: 25,
            Entitlement.MAX_OPEN_POSITIONS: 50,
            Entitlement.MAX_DAILY_EXECUTIONS: 2400,
            Entitlement.MAX_BACKTESTS_PER_DAY: 200,
            Entitlement.STRATEGY_LIBRARY: [
                "trend_following_v1",
                "mean_reversion_v1",
                "breakout_v1",
                "momentum_rotation_v1",
            ],
            Entitlement.BACKTESTING: True,
            Entitlement.STRATEGY_CUSTOMIZATION: True,
            Entitlement.ADVANCED_ANALYTICS: True,
            Entitlement.AUTOMATION: True,
            Entitlement.AUTOMATION_MODE: "background",
            Entitlement.MAX_AUTOMATED_TRADES_PER_DAY: 2400,
            Entitlement.PORTFOLIO_OPTIMIZATION: True,
            Entitlement.PRIORITY_SUPPORT: True,
            Entitlement.PERFORMANCE_FEES: True,
            Entitlement.LIVE_TRADING: True,
            Entitlement.API_ACCESS: True,
        },
    },
    {
        "code": PlanCode.VIP,
        "name": "VIP",
        "tagline": "No VELTRANE trade cap: the venue and your own risk policy set the ceiling.",
        "price_monthly": 349,
        "sort_order": 4,
        "trial_days": 7,
        "features": [
            "Everything in Elite",
            "No VELTRANE daily trade cap — bounded by Deriv's API and your account limits",
            "Background autonomous trading",
            "Highest connection and position limits",
            "Priority support",
        ],
        "limits": {
            Entitlement.MAX_CONNECTIONS: 50,
            Entitlement.MAX_OPEN_POSITIONS: 100,
            # -1 means "no VELTRANE numeric cap". Every deterministic risk rule still applies.
            Entitlement.MAX_DAILY_EXECUTIONS: -1,
            Entitlement.MAX_BACKTESTS_PER_DAY: 500,
            Entitlement.STRATEGY_LIBRARY: [
                "trend_following_v1",
                "mean_reversion_v1",
                "breakout_v1",
                "momentum_rotation_v1",
            ],
            Entitlement.BACKTESTING: True,
            Entitlement.STRATEGY_CUSTOMIZATION: True,
            Entitlement.ADVANCED_ANALYTICS: True,
            Entitlement.AUTOMATION: True,
            Entitlement.AUTOMATION_MODE: "background",
            Entitlement.MAX_AUTOMATED_TRADES_PER_DAY: -1,
            Entitlement.PORTFOLIO_OPTIMIZATION: True,
            Entitlement.PRIORITY_SUPPORT: True,
            Entitlement.PERFORMANCE_FEES: True,
            Entitlement.LIVE_TRADING: True,
            Entitlement.API_ACCESS: True,
        },
    },
]

PAST_DUE_GRACE_DAYS = 3


def _plan_payload(spec: dict) -> dict:
    return {
        "name": spec["name"],
        "tagline": spec["tagline"],
        "price_monthly": spec["price_monthly"],
        "currency": "USD",
        "features": spec["features"],
        "limits": spec["limits"],
        "sort_order": spec["sort_order"],
        "trial_days": spec["trial_days"],
    }


def ensure_plans(db: Session) -> None:
    """Create any plan that is missing. Existing rows are left alone.

    Startup uses this so an administrator's price or limit edits survive a restart. Pushing
    catalog changes to existing rows is an explicit operator action: ``sync_plans``.
    """
    for spec in PLAN_CATALOG:
        if db.get(Plan, spec["code"]) is None:
            db.add(Plan(code=spec["code"], **{**_plan_payload(spec), "is_active": True}))
    db.flush()


def sync_plans(db: Session) -> None:
    """Overwrite every plan with the catalog in this module. Operator action, not startup."""
    for spec in PLAN_CATALOG:
        plan = db.get(Plan, spec["code"])
        payload = {**_plan_payload(spec), "is_active": True}
        if plan is None:
            db.add(Plan(code=spec["code"], **payload))
        else:
            for key, value in payload.items():
                setattr(plan, key, value)
    db.flush()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def active_subscription(db: Session, org_id: str) -> Subscription | None:
    return db.query(Subscription).filter(Subscription.org_id == org_id).order_by(Subscription.created_at.desc()).first()


def effective_plan_code(db: Session, org_id: str) -> str:
    """Resolve the plan a tenant is *actually* entitled to right now."""
    sub = active_subscription(db, org_id)
    if sub is None:
        return PlanCode.FREE
    now = _utcnow()
    if sub.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING):
        if sub.current_period_end and sub.current_period_end < now - timedelta(days=PAST_DUE_GRACE_DAYS):
            return PlanCode.FREE
        return sub.plan_code
    if sub.status == SubscriptionStatus.PAST_DUE:
        anchor = sub.current_period_end or sub.updated_at
        if anchor and anchor > now - timedelta(days=PAST_DUE_GRACE_DAYS):
            return sub.plan_code
        return PlanCode.FREE
    return PlanCode.FREE


def resolve_entitlements(db: Session, org_id: str) -> dict:
    """Effective entitlements = plan limits overlaid with unexpired admin overrides.

    A plan row written before a new limit existed would otherwise answer ``None`` for it and
    silently switch the feature off. Catalogue defaults for that plan code fill the gaps; a
    value an administrator actually stored still wins.
    """
    plan_code = effective_plan_code(db, org_id)
    plan = db.get(Plan, plan_code)
    defaults = next((spec["limits"] for spec in PLAN_CATALOG if spec["code"] == plan_code), {})
    limits = {**defaults, **(plan.limits or {})} if plan else dict(defaults)
    now = _utcnow()
    overrides = (
        db.query(EntitlementOverride)
        .filter(EntitlementOverride.org_id == org_id)
        .filter((EntitlementOverride.expires_at.is_(None)) | (EntitlementOverride.expires_at > now))
        .all()
    )
    applied = []
    for ov in overrides:
        value = ov.value.get("value") if isinstance(ov.value, dict) and "value" in ov.value else ov.value
        limits[ov.key] = value
        applied.append({"key": ov.key, "value": value, "reason": ov.reason, "expires_at": ov.expires_at})
    return {"plan_code": plan_code, "limits": limits, "overrides": applied}


def limit_for(db: Session, org_id: str, key: str, default=None):
    return resolve_entitlements(db, org_id)["limits"].get(key, default)


def has_feature(db: Session, org_id: str, key: str) -> bool:
    return bool(limit_for(db, org_id, key, False))


def require_feature(db: Session, org_id: str, key: str, message: str | None = None) -> None:
    if not has_feature(db, org_id, key):
        raise forbidden(
            "entitlement_required",
            message or f"Your current plan does not include '{key}'. Upgrade to continue.",
        )


def allowed_strategies(db: Session, org_id: str) -> list[str]:
    value = limit_for(db, org_id, Entitlement.STRATEGY_LIBRARY, [])
    return list(value) if isinstance(value, list) else []


def strategy_allowed(db: Session, org_id: str, strategy_code: str) -> bool:
    return strategy_code in allowed_strategies(db, org_id)


def numeric_limit(db: Session, org_id: str, key: str) -> int | None:
    """Return the numeric cap, or None when uncapped (0 or missing)."""
    value = limit_for(db, org_id, key, 0)
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return None if value <= 0 else value


def daily_execution_cap(db: Session, org_id: str) -> int | None:
    """Combined paper/demo + live executions allowed today.

    Three distinct states, deliberately not collapsed into one:

    ``None``  the plan carries no VELTRANE cap (VIP)
    ``0``     the plan cannot execute at all (Free)
    ``n > 0`` at most ``n`` executions today, whichever environment they are placed in

    A naive ``<= 0 means unlimited`` reading would silently hand Free accounts an uncapped
    allowance, which is exactly the bug this helper exists to prevent.
    """
    raw = limit_for(db, org_id, Entitlement.MAX_DAILY_EXECUTIONS, 0)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return None if value < 0 else max(0, value)


def notify_limit_reached(db: Session, org_id: str, title: str, body: str, data: dict | None = None) -> None:
    db.add(
        Notification(
            org_id=org_id,
            category=NotificationCategory.RISK,
            severity=Severity.WARNING,
            title=title,
            body=body,
            data=data or {},
        )
    )
