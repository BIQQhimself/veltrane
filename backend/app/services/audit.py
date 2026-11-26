"""Audit trail. Append-only by convention: nothing in the codebase updates or deletes rows."""
from __future__ import annotations

from datetime import UTC, datetime

from app.db.models import AuditLog
from sqlalchemy.orm import Session

_SENSITIVE_KEYS = {
    "password",
    "api_key",
    "apiKey",
    "secret",
    "passphrase",
    "token",
    "authorization",
    "refresh_token",
    "access_token",
    "mfa_secret",
}


def _scrub(value):
    if isinstance(value, dict):
        return {
            k: ("[redacted]" if k.lower() in {s.lower() for s in _SENSITIVE_KEYS} else _scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def record(
    db: Session,
    *,
    action: str,
    org_id: str | None = None,
    actor_user_id: str | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    meta: dict | None = None,
    flush: bool = True,
) -> AuditLog:
    entry = AuditLog(
        org_id=org_id,
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        actor_role=actor_role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip=ip,
        user_agent=(user_agent or "")[:400] or None,
        meta=_scrub(meta or {}),
        created_at=datetime.now(UTC),
    )
    db.add(entry)
    if flush:
        db.flush()
    return entry
