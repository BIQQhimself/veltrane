"""Business analytics for the admin command centre.

All figures are derived from persisted records. Cost-per-subscriber inputs are
operator-provided settings, not invented numbers.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.constants import PlanCode, SubscriptionStatus
from app.db.models import (
    AiUsage,
    Organization,
    Payment,
    PerformanceFeeRecord,
    Plan,
    Refund,
    Subscription,
    SupportTicket,
    SystemSetting,
    Trade,
    UsageMetric,
    User,
)
from sqlalchemy import func
from sqlalchemy.orm import Session

COST_SETTING_KEY = "cost_model"
DEFAULT_COSTS = {
    "infra_monthly_usd": 0.0,
    "ai_monthly_usd": 0.0,
    "support_cost_per_ticket_usd": 0.0,
    "notes": "Set these to real invoice amounts. Zeros mean 'not configured', not 'free'.",
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def cost_model(db: Session) -> dict:
    row = db.get(SystemSetting, COST_SETTING_KEY)
    value = dict(DEFAULT_COSTS)
    if row and isinstance(row.value, dict):
        value.update(row.value)
    return value


def set_cost_model(db: Session, value: dict) -> dict:
    merged = {**DEFAULT_COSTS, **value}
    row = db.get(SystemSetting, COST_SETTING_KEY)
    if row is None:
        db.add(SystemSetting(key=COST_SETTING_KEY, value=merged, description="Infrastructure/AI/support cost inputs"))
    else:
        row.value = merged
    db.flush()
    return merged


def _active_subs(db: Session) -> list[Subscription]:
    return (
        db.query(Subscription)
        .filter(Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]))
        .all()
    )


def overview(db: Session, *, days: int = 30) -> dict:
    now = _utcnow()
    since = now - timedelta(days=days)
    plans = {p.code: p for p in db.query(Plan).all()}
    subs = _active_subs(db)

    mrr = 0.0
    revenue_by_tier: dict[str, float] = {code: 0.0 for code in plans}
    counts_by_tier: dict[str, int] = {code: 0 for code in plans}
    for sub in subs:
        plan = plans.get(sub.plan_code)
        if plan is None:
            continue
        price = float(plan.price_monthly)
        mrr += price
        revenue_by_tier[sub.plan_code] = revenue_by_tier.get(sub.plan_code, 0.0) + price
        counts_by_tier[sub.plan_code] = counts_by_tier.get(sub.plan_code, 0) + 1

    total_orgs = db.query(func.count(Organization.id)).scalar() or 0
    total_users = db.query(func.count(User.id)).filter(User.status == "active").scalar() or 0
    paid_orgs = sum(counts_by_tier.get(c, 0) for c in (PlanCode.BASIC, PlanCode.PRO, PlanCode.ELITE))

    new_subs = (
        db.query(func.count(Subscription.id))
        .filter(Subscription.created_at >= since, Subscription.plan_code != PlanCode.FREE)
        .scalar()
        or 0
    )
    canceled = db.query(func.count(Subscription.id)).filter(Subscription.canceled_at >= since).scalar() or 0
    churn_rate = (canceled / paid_orgs * 100) if paid_orgs else 0.0
    conversion = (paid_orgs / total_orgs * 100) if total_orgs else 0.0

    payments = (
        db.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(Payment.status.in_(["succeeded", "partially_refunded"]), Payment.created_at >= since)
        .scalar()
        or 0.0
    )
    failed_payments = (
        db.query(func.count(Payment.id)).filter(Payment.status == "failed", Payment.created_at >= since).scalar() or 0
    )
    refunded = db.query(func.coalesce(func.sum(Refund.amount), 0)).filter(Refund.created_at >= since).scalar() or 0.0
    perf_fee_revenue = (
        db.query(func.coalesce(func.sum(PerformanceFeeRecord.fee_amount), 0))
        .filter(PerformanceFeeRecord.status == "invoiced", PerformanceFeeRecord.created_at >= since)
        .scalar()
        or 0.0
    )
    ai_cost = db.query(func.coalesce(func.sum(AiUsage.cost_usd), 0)).filter(AiUsage.created_at >= since).scalar() or 0.0
    costs = cost_model(db)
    monthly_infra = float(costs["infra_monthly_usd"])
    open_tickets = db.query(func.count(SupportTicket.id)).filter(SupportTicket.status == "open").scalar() or 0
    support_cost = open_tickets * float(costs["support_cost_per_ticket_usd"])
    subscriber_count = max(paid_orgs, 1)
    gross_margin = mrr - monthly_infra - ai_cost - support_cost

    demo_executions = (
        db.query(func.coalesce(func.sum(UsageMetric.value), 0))
        .filter(UsageMetric.metric == "demo_executions", UsageMetric.created_at >= since)
        .scalar()
        or 0
    )
    live_orders = db.query(func.count(Trade.id)).filter(Trade.mode == "live", Trade.created_at >= since).scalar() or 0

    return {
        "window_days": days,
        "mrr": round(mrr, 2),
        "arr": round(mrr * 12, 2),
        "revenue_by_tier": {k: round(v, 2) for k, v in revenue_by_tier.items()},
        "subscribers_by_tier": counts_by_tier,
        "organizations": total_orgs,
        "active_users": total_users,
        "paid_subscribers": paid_orgs,
        "new_subscriptions": int(new_subs),
        "cancellations": int(canceled),
        "churn_rate_pct": round(churn_rate, 2),
        "free_to_paid_conversion_pct": round(conversion, 2),
        "payments_collected": round(float(payments), 2),
        "payment_failures": int(failed_payments),
        "refunds": round(float(refunded), 2),
        "performance_fee_revenue": round(float(perf_fee_revenue), 2),
        "ai_cost": round(float(ai_cost), 2),
        "ai_cost_per_subscriber": round(float(ai_cost) / subscriber_count, 2),
        "infra_cost_per_subscriber": round(monthly_infra / subscriber_count, 2),
        "support_cost_per_subscriber": round(support_cost / subscriber_count, 2),
        "contribution_margin": round(gross_margin, 2),
        "contribution_margin_pct": round((gross_margin / mrr * 100) if mrr else 0.0, 2),
        "open_support_tickets": int(open_tickets),
        "demo_executions": int(demo_executions),
        "live_trades": int(live_orders),
        "cost_model": costs,
        "note": "Cost figures use operator-provided inputs. Unset inputs are 0.00 and must not be read as zero cost.",
    }


def revenue_series(db: Session, *, days: int = 90) -> list[dict]:
    since = _utcnow() - timedelta(days=days)
    rows = (
        db.query(
            func.date_trunc("day", Payment.created_at).label("day"),
            func.coalesce(func.sum(Payment.amount), 0).label("amount"),
        )
        .filter(Payment.created_at >= since, Payment.status.in_(["succeeded", "partially_refunded"]))
        .group_by("day")
        .order_by("day")
        .all()
    )
    return [{"date": row.day.date().isoformat(), "amount": round(float(row.amount), 2)} for row in rows]


def subscription_breakdown(db: Session) -> list[dict]:
    plans = {p.code: p for p in db.query(Plan).order_by(Plan.sort_order).all()}
    rows = []
    for code, plan in plans.items():
        count = (
            db.query(func.count(Subscription.id))
            .filter(
                Subscription.plan_code == code,
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]),
            )
            .scalar()
            or 0
        )
        rows.append(
            {
                "plan_code": code,
                "name": plan.name,
                "price_monthly": float(plan.price_monthly),
                "subscribers": int(count),
                "mrr": round(float(plan.price_monthly) * int(count), 2),
            }
        )
    return rows
