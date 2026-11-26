from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.api import serializers
from app.api.deps import get_or_404, require_admin, require_analyst, require_support
from app.api.schemas import (
    CostModelUpdate,
    EntitlementOverrideRequest,
    FeatureFlagUpdate,
    LiveTradingSwitchRequest,
    PerformanceFeeComputeRequest,
    PerformanceFeeSettings,
    PlanUpdateRequest,
    RefundRequest,
    RiskPolicyUpdate,
    TicketReply,
    UserAdminUpdate,
)
from app.core.config import settings
from app.core.errors import bad_request, not_found
from app.core.redis_client import get_redis
from app.db.constants import AuditAction
from app.db.models import (
    AiUsage,
    AuditLog,
    Connection,
    EntitlementOverride,
    FeatureFlag,
    FeeConsent,
    KillSwitch,
    Order,
    Organization,
    Payment,
    PerformanceFeeRecord,
    Plan,
    Refund,
    RiskPolicy,
    Subscription,
    SupportTicket,
    Trade,
    UsageMetric,
    User,
)
from app.db.session import get_db
from app.providers.registry import provider_catalog
from app.risk.types import DEFAULT_RISK_RULES, merged_rules
from app.services import (
    analytics,
    audit,
    billing,
    entitlements,
    kill_switch,
    performance_fees,
    platform_switch,
    strategy_service,
)
from app.services.email import deliver_queued
from app.services.scheduler import scheduler_state
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview")
def overview(
    days: int = Query(default=30, ge=1, le=365), staff: User = Depends(require_analyst), db: Session = Depends(get_db)
):
    return analytics.overview(db, days=days)


@router.get("/revenue")
def revenue(
    days: int = Query(default=90, ge=7, le=365), staff: User = Depends(require_analyst), db: Session = Depends(get_db)
):
    return {
        "series": analytics.revenue_series(db, days=days),
        "breakdown": analytics.subscription_breakdown(db),
        "overview": analytics.overview(db, days=days),
    }


@router.get("/users")
def list_users(
    query: str | None = None,
    limit: int = Query(default=50, le=200),
    staff: User = Depends(require_analyst),
    db: Session = Depends(get_db),
):
    q = db.query(User)
    if query:
        like = f"%{query.lower()}%"
        q = q.filter(func.lower(User.email).like(like) | func.lower(User.full_name).like(like))
    rows = q.order_by(User.created_at.desc()).limit(limit).all()
    org_ids = {u.org_id for u in rows}
    orgs = {o.id: o for o in db.query(Organization).filter(Organization.id.in_(org_ids)).all()} if org_ids else {}
    subs = {}
    if org_ids:
        for sub in db.query(Subscription).filter(Subscription.org_id.in_(org_ids)).all():
            subs.setdefault(sub.org_id, sub)
    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "status": u.status,
                "email_verified": u.email_verified_at is not None,
                "mfa_enabled": u.mfa_enabled,
                "is_staff": u.is_staff,
                "staff_role": u.staff_role,
                "org_id": u.org_id,
                "org_name": orgs[u.org_id].name if u.org_id in orgs else None,
                "plan_code": subs[u.org_id].plan_code if u.org_id in subs else "free",
                "subscription_status": subs[u.org_id].status if u.org_id in subs else None,
                "last_login_at": serializers.iso(u.last_login_at),
                "created_at": serializers.iso(u.created_at),
            }
            for u in rows
        ],
        "count": len(rows),
    }


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    payload: UserAdminUpdate,
    staff: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = get_or_404(db, User, user_id)
    if target is None:
        raise not_found("user_not_found", "User not found.")
    changes = {}
    if payload.status:
        target.status = payload.status
        changes["status"] = payload.status
    if payload.is_staff is not None:
        target.is_staff = payload.is_staff
        changes["is_staff"] = payload.is_staff
        if not payload.is_staff:
            target.staff_role = None
    if payload.staff_role:
        if staff.staff_role != "owner" and payload.staff_role == "owner":
            raise bad_request("role_not_allowed", "Only an owner can grant the owner role.")
        target.staff_role = payload.staff_role
        target.is_staff = True
        changes["staff_role"] = payload.staff_role
    audit.record(
        db,
        action=AuditAction.ADMIN_ACTION,
        actor_user_id=staff.id,
        actor_email=staff.email,
        actor_role=staff.staff_role,
        target_type="user",
        target_id=target.id,
        meta={"changes": changes, "reason": payload.reason},
    )
    db.commit()
    return {"status": "updated", "changes": changes}


@router.get("/subscriptions")
def subscriptions(staff: User = Depends(require_analyst), db: Session = Depends(get_db)):
    rows = db.query(Subscription).order_by(Subscription.created_at.desc()).limit(200).all()
    orgs = {o.id: o for o in db.query(Organization).all()}
    return {
        "subscriptions": [
            {
                "id": s.id,
                "org_id": s.org_id,
                "org_name": orgs[s.org_id].name if s.org_id in orgs else None,
                "plan_code": s.plan_code,
                "status": s.status,
                "provider": s.provider,
                "current_period_end": serializers.iso(s.current_period_end),
                "cancel_at_period_end": s.cancel_at_period_end,
                "pending_plan_code": s.pending_plan_code,
                "created_at": serializers.iso(s.created_at),
            }
            for s in rows
        ]
    }


@router.get("/payments")
def payments(staff: User = Depends(require_analyst), db: Session = Depends(get_db)):
    rows = db.query(Payment).order_by(Payment.created_at.desc()).limit(200).all()
    refunds = db.query(Refund).order_by(Refund.created_at.desc()).limit(100).all()
    return {
        "payments": [
            {
                "id": p.id,
                "org_id": p.org_id,
                "amount": float(p.amount),
                "currency": p.currency,
                "status": p.status,
                "provider": p.provider,
                "refunded_amount": float(p.refunded_amount or 0),
                "created_at": serializers.iso(p.created_at),
            }
            for p in rows
        ],
        "refunds": [
            {
                "id": r.id,
                "payment_id": r.payment_id,
                "amount": float(r.amount),
                "status": r.status,
                "reason": r.reason,
                "created_at": serializers.iso(r.created_at),
            }
            for r in refunds
        ],
    }


@router.post("/refunds")
def issue_refund(payload: RefundRequest, staff: User = Depends(require_admin), db: Session = Depends(get_db)):
    refund = billing.issue_refund(
        db, payment_id=payload.payment_id, amount=payload.amount, reason=payload.reason, actor=staff
    )
    db.commit()
    return {"id": refund.id, "status": refund.status, "amount": float(refund.amount)}


@router.get("/plans")
def admin_plans(staff: User = Depends(require_analyst), db: Session = Depends(get_db)):
    rows = db.query(Plan).order_by(Plan.sort_order).all()
    return {
        "plans": [
            {
                "code": p.code,
                "name": p.name,
                "tagline": p.tagline,
                "price_monthly": float(p.price_monthly),
                "currency": p.currency,
                "features": p.features,
                "limits": p.limits,
                "is_active": p.is_active,
                "trial_days": p.trial_days,
            }
            for p in rows
        ],
        "editable": ["price_monthly", "is_active", "features", "limits", "tagline"],
    }


@router.patch("/plans/{code}")
def update_plan(
    code: str, payload: PlanUpdateRequest, staff: User = Depends(require_admin), db: Session = Depends(get_db)
):
    plan = db.get(Plan, code)
    if plan is None:
        raise not_found("plan_not_found", "Plan not found.")
    changes = {}
    if payload.price_monthly is not None:
        plan.price_monthly = payload.price_monthly
        changes["price_monthly"] = payload.price_monthly
    if payload.is_active is not None:
        plan.is_active = payload.is_active
        changes["is_active"] = payload.is_active
    if payload.features is not None:
        plan.features = payload.features
        changes["features"] = payload.features
    if payload.limits is not None:
        plan.limits = {**(plan.limits or {}), **payload.limits}
        changes["limits"] = plan.limits
    if payload.tagline is not None:
        plan.tagline = payload.tagline
        changes["tagline"] = payload.tagline
    audit.record(
        db,
        action=AuditAction.ADMIN_ACTION,
        actor_user_id=staff.id,
        actor_email=staff.email,
        actor_role=staff.staff_role,
        target_type="plan",
        target_id=code,
        meta={"changes": changes},
    )
    db.commit()
    return {"status": "updated", "changes": changes}


@router.get("/entitlements/{org_id}")
def org_entitlements(org_id: str, staff: User = Depends(require_analyst), db: Session = Depends(get_db)):
    org = get_or_404(db, Organization, org_id)
    if org is None:
        raise not_found("org_not_found", "Organization not found.")
    return {"org_id": org_id, **entitlements.resolve_entitlements(db, org_id)}


@router.post("/entitlements/override", status_code=201)
def create_override(
    payload: EntitlementOverrideRequest, staff: User = Depends(require_admin), db: Session = Depends(get_db)
):
    org = db.get(Organization, payload.org_id)
    if org is None:
        raise not_found("org_not_found", "Organization not found.")
    override = EntitlementOverride(
        org_id=payload.org_id,
        key=payload.key,
        value={"value": payload.value},
        reason=payload.reason,
        expires_at=payload.expires_at,
        created_by=staff.id,
    )
    db.add(override)
    audit.record(
        db,
        action=AuditAction.ADMIN_ACTION,
        actor_user_id=staff.id,
        actor_email=staff.email,
        actor_role=staff.staff_role,
        org_id=payload.org_id,
        target_type="entitlement_override",
        target_id=payload.key,
        meta={"value": payload.value, "reason": payload.reason},
    )
    db.commit()
    return {"status": "created", "id": override.id}


@router.get("/connections")
def all_connections(staff: User = Depends(require_analyst), db: Session = Depends(get_db)):
    rows = db.query(Connection).order_by(Connection.created_at.desc()).limit(300).all()
    return {
        "connections": [
            {
                "id": c.id,
                "org_id": c.org_id,
                "provider": c.provider,
                "label": c.label,
                "environment": c.environment,
                "status": c.status,
                "permissions": c.permissions,
                "last_sync_at": serializers.iso(c.last_sync_at),
                "last_error": c.last_error,
            }
            for c in rows
        ],
        "note": "Credential material is never exposed to staff. Only key hints and rotation timestamps exist in the user UI.",
    }


@router.get("/trading/activity")
def trading_activity(staff: User = Depends(require_analyst), db: Session = Depends(get_db)):
    orders = db.query(Order).order_by(Order.created_at.desc()).limit(200).all()
    trades = db.query(Trade).order_by(Trade.closed_at.desc()).limit(200).all()
    rejected = db.query(func.count(Order.id)).filter(Order.status == "rejected").scalar() or 0
    return {
        "orders": [
            {
                "id": o.id,
                "org_id": o.org_id,
                "symbol": o.instrument_symbol,
                "side": o.side,
                "mode": o.mode,
                "is_demo": o.is_demo,
                "status": o.status,
                "rejection_reason": o.rejection_reason,
                "created_at": serializers.iso(o.created_at),
            }
            for o in orders
        ],
        "trades": [
            {
                "id": t.id,
                "org_id": t.org_id,
                "symbol": t.instrument_symbol,
                "mode": t.mode,
                "is_demo": t.is_demo,
                "net_pnl": float(t.net_pnl),
                "closed_at": serializers.iso(t.closed_at),
            }
            for t in trades
        ],
        "rejected_orders_total": int(rejected),
        "note": "Paper activity is flagged is_demo. Live trades require platform enablement and per-user authorisation.",
    }


@router.get("/risk/policy")
def get_risk_policy(staff: User = Depends(require_analyst), db: Session = Depends(get_db)):
    policy = (
        db.query(RiskPolicy)
        .filter(RiskPolicy.org_id.is_(None), RiskPolicy.is_active.is_(True))
        .order_by(RiskPolicy.version.desc())
        .first()
    )
    return {
        "policy": {
            "id": policy.id if policy else None,
            "version": policy.version if policy else 0,
            "rules": merged_rules(policy.rules if policy else None),
            "defaults": DEFAULT_RISK_RULES,
        }
    }


@router.put("/risk/policy")
def update_risk_policy(payload: RiskPolicyUpdate, staff: User = Depends(require_admin), db: Session = Depends(get_db)):
    current = (
        db.query(RiskPolicy)
        .filter(RiskPolicy.org_id.is_(None), RiskPolicy.is_active.is_(True))
        .order_by(RiskPolicy.version.desc())
        .first()
    )
    rules = merged_rules(payload.rules)
    for key, value in payload.rules.items():
        if key not in DEFAULT_RISK_RULES:
            raise bad_request("unknown_rule", f"Unknown risk rule '{key}'.")
        if not isinstance(value, (int, float, bool)):
            raise bad_request("invalid_rule_value", f"Rule '{key}' must be numeric or boolean.")
    if current:
        current.is_active = False
    new_policy = RiskPolicy(
        org_id=None,
        name="global",
        version=(current.version + 1) if current else 1,
        rules=rules,
        is_active=True,
        updated_by=staff.id,
    )
    db.add(new_policy)
    audit.record(
        db,
        action=AuditAction.RISK_POLICY_UPDATED,
        actor_user_id=staff.id,
        actor_email=staff.email,
        actor_role=staff.staff_role,
        target_type="risk_policy",
        target_id=new_policy.id,
        meta={"version": new_policy.version, "changes": payload.rules, "reason": payload.reason},
    )
    db.commit()
    return {"status": "updated", "version": new_policy.version, "rules": rules}


@router.get("/kill-switches")
def kill_switches(staff: User = Depends(require_analyst), db: Session = Depends(get_db)):
    rows = db.query(KillSwitch).order_by(KillSwitch.updated_at.desc()).limit(100).all()
    return {
        "switches": [
            {
                "id": s.id,
                "scope": s.scope,
                "target": s.target,
                "engaged": s.engaged,
                "reason": s.reason,
                "engaged_at": serializers.iso(s.engaged_at),
                "released_at": serializers.iso(s.released_at),
            }
            for s in rows
        ],
        "global_state": kill_switch.state_for(db, org_id="__none__"),
        "platform_live_enabled": platform_switch.effective(db),
        "live_trading_switch": platform_switch.state(db),
    }


@router.post("/kill-switches/engage")
def engage_kill(payload: RiskPolicyUpdate, staff: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Engage the global halt. Uses the same durable switch the risk engine reads."""
    switch = kill_switch.engage(db, scope="global", target="all", actor=staff, reason=payload.reason)
    db.commit()
    return {"status": "engaged", "scope": switch.scope, "engaged_at": serializers.iso(switch.engaged_at)}


@router.post("/kill-switches/release")
def release_kill(payload: RiskPolicyUpdate, staff: User = Depends(require_admin), db: Session = Depends(get_db)):
    switch = kill_switch.release(db, scope="global", target="all", actor=staff, reason=payload.reason)
    db.commit()
    return {"status": "released", "scope": switch.scope}


@router.get("/live-trading")
def live_trading_state(staff: User = Depends(require_admin), db: Session = Depends(get_db)):
    return platform_switch.state(db)


@router.put("/live-trading")
def set_live_trading(
    payload: LiveTradingSwitchRequest,
    staff: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Owner/Admin key for platform-wide live execution.

    The deployment flag stays with the operator, so this switch can always stop live
    trading and can only start it when the operator has already enabled the deployment
    level. Requires a typed confirmation and a reason, and is audit logged.
    """
    expected = "ENABLE LIVE TRADING" if payload.enabled else "DISABLE LIVE TRADING"
    if payload.confirm.strip().upper() != expected:
        raise bad_request("confirmation_mismatch", f'Type "{expected}" to confirm this change.')
    if payload.enabled and not settings.live_trading_enabled:
        raise bad_request(
            "deployment_flag_off",
            "This deployment has live trading switched off. An operator must set VELTRANE_LIVE_TRADING_ENABLED "
            "before the in-app switch can enable live execution.",
        )
    return platform_switch.set_staff(db, user=staff, enabled=payload.enabled, reason=payload.reason)


@router.get("/feature-flags")
def feature_flags(staff: User = Depends(require_analyst), db: Session = Depends(get_db)):
    rows = db.query(FeatureFlag).order_by(FeatureFlag.key).all()
    return {
        "flags": [
            {
                "key": f.key,
                "enabled": f.enabled,
                "description": f.description,
                "rollout": f.rollout,
                "updated_at": serializers.iso(f.updated_at),
            }
            for f in rows
        ]
    }


@router.put("/feature-flags/{key}")
def upsert_flag(
    key: str, payload: FeatureFlagUpdate, staff: User = Depends(require_admin), db: Session = Depends(get_db)
):
    flag = db.get(FeatureFlag, key)
    if flag is None:
        flag = FeatureFlag(
            key=key, enabled=payload.enabled, description=payload.description or "", rollout=payload.rollout or {}
        )
        db.add(flag)
    else:
        flag.enabled = payload.enabled
        if payload.description is not None:
            flag.description = payload.description
        if payload.rollout is not None:
            flag.rollout = payload.rollout
    flag.updated_by = staff.id
    audit.record(
        db,
        action=AuditAction.FEATURE_FLAG_CHANGED,
        actor_user_id=staff.id,
        actor_role=staff.staff_role,
        target_type="feature_flag",
        target_id=key,
        meta={"enabled": payload.enabled},
    )
    db.commit()
    return {"status": "updated", "key": key, "enabled": payload.enabled}


@router.get("/audit")
def audit_log(
    action: str | None = None,
    limit: int = Query(default=100, le=500),
    staff: User = Depends(require_analyst),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    rows = q.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return {
        "entries": [
            {
                "id": a.id,
                "org_id": a.org_id,
                "actor_email": a.actor_email,
                "actor_role": a.actor_role,
                "action": a.action,
                "target_type": a.target_type,
                "target_id": a.target_id,
                "ip": a.ip,
                "meta": a.meta,
                "created_at": serializers.iso(a.created_at),
            }
            for a in rows
        ]
    }


@router.get("/system/health")
def system_health(staff: User = Depends(require_analyst), db: Session = Depends(get_db)):
    from sqlalchemy import text

    db_ok = True
    try:
        db.execute(text("select 1"))
    except Exception:  # noqa: BLE001
        db_ok = False
    redis_ok = get_redis() is not None
    queued_email = (
        db.query(func.count())
        .select_from(__import__("app.db.models", fromlist=["EmailOutbox"]).EmailOutbox)
        .filter_by(status="queued")
        .scalar()
        or 0
    )
    return {
        "database": {"ok": db_ok},
        "redis": {"ok": redis_ok, "note": "Rate limiting and caching degrade gracefully when Redis is unavailable."},
        "live_trading_enabled": platform_switch.effective(db),
        "live_trading_switch": platform_switch.state(db),
        "billing_provider": settings.billing_provider,
        "market_data_source": settings.market_data_source,
        "providers": provider_catalog(),
        "paper_scheduler": scheduler_state(),
        "queued_emails": int(queued_email),
        "email_delivery": "outbox_only" if settings.env != "production" else "provider_required",
        "version": "0.1.0",
    }


@router.get("/usage")
def usage_metrics(staff: User = Depends(require_analyst), db: Session = Depends(get_db)):
    rows = db.query(UsageMetric.metric, func.sum(UsageMetric.value)).group_by(UsageMetric.metric).all()
    ai = db.query(
        func.coalesce(func.sum(AiUsage.cost_usd), 0), func.coalesce(func.sum(AiUsage.tokens_in + AiUsage.tokens_out), 0)
    ).first()
    return {
        "metrics": {metric: float(total) for metric, total in rows},
        "ai_cost_usd": float(ai[0] or 0),
        "ai_tokens": int(ai[1] or 0),
        "note": "AI usage is recorded only when an AI provider is wired in. This build ships deterministic strategies.",
    }


@router.get("/costs")
def get_costs(staff: User = Depends(require_analyst), db: Session = Depends(get_db)):
    return {"cost_model": analytics.cost_model(db)}


@router.put("/costs")
def set_costs(payload: CostModelUpdate, staff: User = Depends(require_admin), db: Session = Depends(get_db)):
    value = analytics.set_cost_model(db, payload.model_dump())
    audit.record(
        db,
        action=AuditAction.ADMIN_ACTION,
        actor_user_id=staff.id,
        actor_role=staff.staff_role,
        target_type="cost_model",
        meta=value,
    )
    db.commit()
    return {"cost_model": value}


@router.get("/performance-fees")
def get_perf_fees(staff: User = Depends(require_analyst), db: Session = Depends(get_db)):
    rows = db.query(PerformanceFeeRecord).order_by(PerformanceFeeRecord.created_at.desc()).limit(100).all()
    return {
        "settings": performance_fees.settings_for(db),
        "records": [
            {
                "id": r.id,
                "org_id": r.org_id,
                "period_start": serializers.iso(r.period_start),
                "period_end": serializers.iso(r.period_end),
                "realized_pnl": float(r.realized_pnl),
                "hwm_before": float(r.hwm_before),
                "hwm_after": float(r.hwm_after),
                "fee_rate": float(r.fee_rate),
                "fee_amount": float(r.fee_amount),
                "status": r.status,
                "calculation": r.calculation,
            }
            for r in rows
        ],
        "consents": db.query(func.count(FeeConsent.id)).scalar() or 0,
        "note": "Performance fees are disabled by default and cannot be enabled until legal review is recorded.",
    }


@router.put("/performance-fees/settings")
def update_perf_settings(
    payload: PerformanceFeeSettings, staff: User = Depends(require_admin), db: Session = Depends(get_db)
):
    value = performance_fees.update_settings(db, value=payload.model_dump(), actor=staff)
    db.commit()
    return {"settings": value}


@router.post("/performance-fees/compute", status_code=201)
def compute_perf_fee(
    payload: PerformanceFeeComputeRequest, staff: User = Depends(require_admin), db: Session = Depends(get_db)
):
    record = performance_fees.compute_fee(
        db, org_id=payload.org_id, period_start=payload.period_start, period_end=payload.period_end, actor=staff
    )
    db.commit()
    return {
        "id": record.id,
        "fee_amount": float(record.fee_amount),
        "status": record.status,
        "calculation": record.calculation,
    }


@router.post("/performance-fees/{record_id}/invoice")
def invoice_perf_fee(record_id: str, staff: User = Depends(require_admin), db: Session = Depends(get_db)):
    record = get_or_404(db, PerformanceFeeRecord, record_id)
    if record is None:
        raise not_found("record_not_found", "Performance fee record not found.")
    performance_fees.mark_invoiced(db, record=record, actor=staff)
    db.commit()
    return {"status": record.status, "fee_amount": float(record.fee_amount)}


@router.post("/strategies/{version_id}/promote-live")
def promote_strategy(
    version_id: str, payload: RiskPolicyUpdate, staff: User = Depends(require_admin), db: Session = Depends(get_db)
):
    version = strategy_service.promote_to_live(db, actor=staff, version_id=version_id, reason=payload.reason)
    db.commit()
    return {"status": version.status, "version_id": version.id}


@router.get("/support/tickets")
def support_tickets(status: str | None = None, staff: User = Depends(require_support), db: Session = Depends(get_db)):
    q = db.query(SupportTicket)
    if status:
        q = q.filter(SupportTicket.status == status)
    rows = q.order_by(SupportTicket.created_at.desc()).limit(100).all()
    return {
        "tickets": [
            {
                "id": t.id,
                "org_id": t.org_id,
                "subject": t.subject,
                "status": t.status,
                "priority": t.priority,
                "messages": t.messages,
                "created_at": serializers.iso(t.created_at),
            }
            for t in rows
        ]
    }


@router.post("/support/tickets/{ticket_id}/reply")
def reply_ticket(
    ticket_id: str, payload: TicketReply, staff: User = Depends(require_support), db: Session = Depends(get_db)
):
    ticket = get_or_404(db, SupportTicket, ticket_id)
    if ticket is None:
        raise not_found("ticket_not_found", "Ticket not found.")
    ticket.messages = [
        *(ticket.messages or []),
        {
            "role": "staff",
            "message": payload.message,
            "at": datetime.now(UTC).isoformat(),
            "staff_email": staff.email,
        },
    ]
    if payload.status:
        ticket.status = payload.status
    audit.record(
        db,
        action=AuditAction.ADMIN_ACTION,
        actor_user_id=staff.id,
        actor_role=staff.staff_role,
        target_type="support_ticket",
        target_id=ticket.id,
        meta={"action": "reply"},
    )
    db.commit()
    return {"status": ticket.status}


@router.get("/fraud/signals")
def fraud_signals(staff: User = Depends(require_analyst), db: Session = Depends(get_db)):
    since = datetime.now(UTC) - timedelta(days=7)
    failed_logins = (
        db.query(AuditLog.ip, func.count(AuditLog.id))
        .filter(AuditLog.action == AuditAction.USER_LOGIN_FAILED, AuditLog.created_at >= since)
        .group_by(AuditLog.ip)
        .having(func.count(AuditLog.id) >= 5)
        .all()
    )
    webhook_rejects = (
        db.query(func.count(AuditLog.id))
        .filter(AuditLog.action == "billing.webhook_rejected", AuditLog.created_at >= since)
        .scalar()
        or 0
    )
    refunds = db.query(func.count(Refund.id)).filter(Refund.created_at >= since).scalar() or 0
    return {
        "failed_login_ips": [{"ip": ip, "attempts": count} for ip, count in failed_logins],
        "webhook_signature_rejections": int(webhook_rejects),
        "recent_refunds": int(refunds),
        "note": "Heuristic signals only. No automated account action is taken from this view.",
    }


@router.post("/maintenance/deliver-emails")
def deliver_emails(staff: User = Depends(require_admin), db: Session = Depends(get_db)):
    pending = deliver_queued(db)
    return {
        "queued": pending,
        "delivered": 0,
        "note": "No SMTP/API provider is configured in this build. Messages remain queued; nothing is marked sent.",
    }
