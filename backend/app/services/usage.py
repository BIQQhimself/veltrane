from __future__ import annotations

from datetime import UTC, date, datetime

from app.db.models import UsageMetric
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _today() -> str:
    return date.today().isoformat()


def get_usage(db: Session, org_id: str, metric: str, period: str | None = None) -> float:
    row = (
        db.query(UsageMetric)
        .filter(
            UsageMetric.org_id == org_id,
            UsageMetric.metric == metric,
            UsageMetric.period == (period or _today()),
        )
        .first()
    )
    return float(row.value) if row else 0.0


def increment_usage(db: Session, org_id: str, metric: str, amount: float = 1.0, meta: dict | None = None) -> float:
    period = _today()
    row = (
        db.query(UsageMetric)
        .filter(
            UsageMetric.org_id == org_id,
            UsageMetric.metric == metric,
            UsageMetric.period == period,
        )
        .with_for_update()
        .first()
    )
    if row is None:
        row = UsageMetric(org_id=org_id, metric=metric, period=period, value=0, meta=meta or {})
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            row = (
                db.query(UsageMetric)
                .filter(
                    UsageMetric.org_id == org_id,
                    UsageMetric.metric == metric,
                    UsageMetric.period == period,
                )
                .with_for_update()
                .one()
            )
    row.value = float(row.value) + amount
    if meta:
        row.meta = {**(row.meta or {}), **meta}
    db.flush()
    return float(row.value)


def remaining_today(db: Session, org_id: str, metric: str, limit: int | None) -> int | None:
    if limit is None:
        return None
    return max(0, limit - int(get_usage(db, org_id, metric)))


def utcnow() -> datetime:
    return datetime.now(UTC)
