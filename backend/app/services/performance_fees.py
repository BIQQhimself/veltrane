"""Performance fees — Elite only, realised P&L only, high-water mark, disabled by default.

Safety properties:
* The module is inert unless the operator enables it AND the tenant has an active consent.
* Fees are computed on **realised, net-of-cost** P&L only; unrealised gains never count.
* A high-water mark means no fee until prior losses are recovered.
* Every computation is stored with its full breakdown; nothing is auto-charged.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.errors import bad_request, forbidden
from app.db.constants import AuditAction, Entitlement, NotificationCategory, Severity
from app.db.models import (
    FeeConsent,
    HighWaterMark,
    Organization,
    PerformanceFeeRecord,
    SystemSetting,
    Trade,
    User,
)
from app.services import audit, entitlements, notifications
from sqlalchemy import func
from sqlalchemy.orm import Session

SETTING_KEY = "performance_fees"
DOCUMENT_VERSION = "perf-fee-terms-2026-01"
DEFAULT_SETTINGS = {
    "enabled": False,
    "rate": 0.20,
    "currency": "USD",
    "min_realized_pnl": 0.0,
    "jurisdictions_allowed": [],
    "legal_review_completed": False,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def settings_for(db: Session) -> dict:
    row = db.get(SystemSetting, SETTING_KEY)
    value = dict(DEFAULT_SETTINGS)
    if row and isinstance(row.value, dict):
        value.update(row.value)
    return value


def update_settings(db: Session, *, value: dict, actor: User) -> dict:
    row = db.get(SystemSetting, SETTING_KEY)
    merged = {**DEFAULT_SETTINGS, **value}
    if merged.get("enabled") and not merged.get("legal_review_completed"):
        raise bad_request(
            "legal_review_required",
            "Performance fees cannot be enabled before legal and regulatory review is recorded.",
        )
    if row is None:
        row = SystemSetting(key=SETTING_KEY, value=merged, description="Elite performance fee configuration")
        db.add(row)
    else:
        row.value = merged
        row.updated_by = actor.id
    db.flush()
    audit.record(
        db,
        action=AuditAction.ADMIN_ACTION,
        actor_user_id=actor.id,
        actor_email=actor.email,
        actor_role=actor.staff_role,
        target_type="system_setting",
        target_id=SETTING_KEY,
        meta={"value": merged},
    )
    return merged


def consent_for(db: Session, org_id: str) -> FeeConsent | None:
    return (
        db.query(FeeConsent)
        .filter(FeeConsent.org_id == org_id, FeeConsent.revoked_at.is_(None))
        .order_by(FeeConsent.accepted_at.desc())
        .first()
    )


def record_consent(
    db: Session, *, user: User, accepted: bool, fee_rate: float, ip: str | None, snapshot: dict | None = None
) -> FeeConsent:
    if not entitlements.has_feature(db, user.org_id, Entitlement.PERFORMANCE_FEES):
        raise forbidden("entitlement_required", "Performance fee agreements are available on Elite only.")
    if not accepted:
        raise bad_request("consent_required", "Explicit consent is required.")
    settings = settings_for(db)
    if not settings.get("legal_review_completed"):
        raise bad_request(
            "legal_review_required",
            "Performance fee agreements are not yet enabled: legal and regulatory review is incomplete.",
        )
    allowed = [code.upper() for code in (settings.get("jurisdictions_allowed") or [])]
    org = db.get(Organization, user.org_id)
    country = (org.country if org and org.country else (user.preferences or {}).get("country") or "").upper()
    if allowed and country not in allowed:
        raise forbidden(
            "jurisdiction_not_allowed",
            "Performance fee agreements are not offered in your jurisdiction.",
        )
    existing = consent_for(db, user.org_id)
    if existing:
        existing.revoked_at = _utcnow()
    consent = FeeConsent(
        org_id=user.org_id,
        user_id=user.id,
        document_version=DOCUMENT_VERSION,
        fee_rate=float(fee_rate),
        accepted_at=_utcnow(),
        ip=ip,
        snapshot={
            "terms_version": DOCUMENT_VERSION,
            "fee_rate": fee_rate,
            "hwm": "Fees apply only to realised net P&L above the previous high-water mark.",
            "extra": snapshot or {},
        },
    )
    db.add(consent)
    db.flush()
    audit.record(
        db,
        action=AuditAction.ADMIN_ACTION,
        org_id=user.org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        target_type="fee_consent",
        target_id=consent.id,
        ip=ip,
        meta={"fee_rate": fee_rate, "document": DOCUMENT_VERSION},
    )
    return consent


def get_hwm(db: Session, org_id: str) -> HighWaterMark:
    hwm = (
        db.query(HighWaterMark)
        .filter(HighWaterMark.org_id == org_id, HighWaterMark.scope == "org")
        .first()
    )
    if hwm is None:
        hwm = HighWaterMark(org_id=org_id, scope="org", value=0.0, as_of=_utcnow())
        db.add(hwm)
        db.flush()
    return hwm


def compute_fee(db: Session, *, org_id: str, period_start: datetime, period_end: datetime, actor: User | None = None) -> PerformanceFeeRecord:
    settings = settings_for(db)
    if not settings.get("enabled"):
        raise bad_request("performance_fees_disabled", "Performance fees are disabled by the operator.")
    consent = consent_for(db, org_id)
    if consent is None:
        raise bad_request("consent_missing", "No active performance fee consent for this account.")
    if consent.accepted_at > period_start:
        raise bad_request("consent_precedes_period", "Consent must predate the fee period.")

    realized = float(
        db.query(func.coalesce(func.sum(Trade.net_pnl), 0))
        .filter(
            Trade.org_id == org_id,
            Trade.closed_at >= period_start,
            Trade.closed_at <= period_end,
        )
        .scalar()
        or 0.0
    )
    hwm = get_hwm(db, org_id)
    hwm_before = float(hwm.value)
    cumulative = hwm_before + realized
    fee_amount = 0.0
    if cumulative > hwm_before and cumulative > 0:
        fee_amount = max(0.0, (cumulative - max(hwm_before, 0.0)) * float(consent.fee_rate))
    hwm_after = max(hwm_before, cumulative) if realized > 0 else hwm_before

    record = PerformanceFeeRecord(
        org_id=org_id,
        period_start=period_start,
        period_end=period_end,
        realized_pnl=realized,
        hwm_before=hwm_before,
        hwm_after=hwm_after,
        fee_rate=float(consent.fee_rate),
        fee_amount=round(fee_amount, 2),
        currency=settings.get("currency", "USD"),
        status="draft",
        consent_id=consent.id,
        calculation={
            "formula": "fee = max(0, (hwm_before + realised_pnl - max(hwm_before, 0)) * rate)",
            "realised_pnl_only": True,
            "unrealised_excluded": True,
            "trades_considered": db.query(Trade)
            .filter(Trade.org_id == org_id, Trade.closed_at >= period_start, Trade.closed_at <= period_end)
            .count(),
            "settings_snapshot": settings,
            "computed_at": _utcnow().isoformat(),
        },
        notes="Draft only. No charge is made automatically; invoicing requires operator action and user notice.",
    )
    db.add(record)
    db.flush()
    audit.record(
        db,
        action=AuditAction.ADMIN_ACTION,
        org_id=org_id,
        actor_user_id=actor.id if actor else None,
        target_type="performance_fee",
        target_id=record.id,
        meta={"fee_amount": float(record.fee_amount), "realized_pnl": float(realized), "status": "draft"},
    )
    return record


def mark_invoiced(db: Session, *, record: PerformanceFeeRecord, actor: User) -> PerformanceFeeRecord:
    if record.status != "draft":
        raise bad_request("invalid_status", f"Record is {record.status}, not draft.")
    record.status = "invoiced"
    hwm = get_hwm(db, record.org_id)
    hwm.value = float(record.hwm_after)
    hwm.as_of = _utcnow()
    db.flush()
    audit.record(
        db,
        action=AuditAction.ADMIN_ACTION,
        org_id=record.org_id,
        actor_user_id=actor.id,
        actor_email=actor.email,
        actor_role=actor.staff_role,
        target_type="performance_fee",
        target_id=record.id,
        meta={"action": "invoiced", "fee_amount": float(record.fee_amount)},
    )
    notifications.notify(
        db,
        org_id=record.org_id,
        category=NotificationCategory.BILLING,
        severity=Severity.WARNING,
        title="Performance fee invoice issued",
        body=(
            f"A performance fee of {record.fee_amount:.2f} {record.currency} was issued for realised net P&L "
            f"between {record.period_start.date()} and {record.period_end.date()}."
        ),
        email=True,
    )
    return record
