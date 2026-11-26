"""Kill switches — the last line of defence.

Three independent carriers so a halt survives a crashed API, a lost Redis, or a
stale deployment:

1. PostgreSQL row in ``kill_switches`` (durable, authoritative).
2. Redis key (fast path, mirrored).
3. Optional file flag (``VELTRANE_KILL_SWITCH_FILE``) that any process can create,
   including the standalone ``scripts/kill_all.py`` CLI with no API running.

Engaging any carrier halts new orders. Exits/closes are still permitted by the risk
engine so users can reduce risk during a halt.
"""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from app.core.redis_client import cache_delete, cache_set, get_redis
from app.db.constants import AuditAction, KillScope, NotificationCategory, Severity
from app.db.models import KillSwitch, User
from app.services import audit, notifications
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)
GLOBAL_TARGET = "all"
REDIS_KEY = "veltrane:kill:{scope}:{target}"
FILE_FLAG_ENV = "VELTRANE_KILL_SWITCH_FILE"


def utcnow() -> datetime:
    return datetime.now(UTC)


def _file_flag_present() -> bool:
    path = os.environ.get(FILE_FLAG_ENV, "")
    return bool(path) and os.path.exists(path)


def _mirror(scope: str, target: str, engaged: bool) -> None:
    key = REDIS_KEY.format(scope=scope, target=target)
    if engaged:
        cache_set(key, "1", 60 * 60 * 24 * 30)
    else:
        cache_delete(key)


def get_switch(db: Session, scope: str, target: str) -> KillSwitch | None:
    return (
        db.query(KillSwitch)
        .filter(KillSwitch.scope == scope, KillSwitch.target == target)
        .first()
    )


def is_engaged(db: Session, scope: str, target: str) -> bool:
    if scope == KillScope.GLOBAL:
        if _file_flag_present():
            return True
        client = get_redis()
        if client is not None:
            try:
                if client.get(REDIS_KEY.format(scope=scope, target=target)) == "1":
                    return True
            except Exception:  # noqa: BLE001 - Redis is a fast path, not the authority
                pass
    switch = get_switch(db, scope, target)
    return bool(switch and switch.engaged)


def engage(
    db: Session,
    *,
    scope: str,
    target: str,
    actor: User | None,
    reason: str,
    notify_org: str | None = None,
) -> KillSwitch:
    switch = get_switch(db, scope, target)
    now = utcnow()
    if switch is None:
        switch = KillSwitch(scope=scope, target=target)
        db.add(switch)
    switch.engaged = True
    switch.reason = reason[:400]
    switch.engaged_by = actor.id if actor else None
    switch.engaged_at = now
    switch.released_at = None
    db.flush()
    _mirror(scope, target, True)
    audit.record(
        db,
        action=AuditAction.KILL_SWITCH_ENGAGED,
        org_id=notify_org or (target if scope == KillScope.ORG else None),
        actor_user_id=actor.id if actor else None,
        actor_email=actor.email if actor else None,
        actor_role=actor.staff_role if actor else None,
        target_type="kill_switch",
        target_id=f"{scope}:{target}",
        meta={"reason": reason},
    )
    if notify_org:
        notifications.notify(
            db,
            org_id=notify_org,
            category=NotificationCategory.RISK,
            severity=Severity.CRITICAL,
            title="AI trading halted",
            body=f"Trading was halted by an operator: {reason}. New entries are blocked; exits remain available.",
        )
    log.warning("kill_switch_engaged", extra={"extra_fields": {"scope": scope, "target": target, "reason": reason}})
    return switch


def release(db: Session, *, scope: str, target: str, actor: User | None, reason: str = "") -> KillSwitch:
    switch = get_switch(db, scope, target)
    if switch is None:
        switch = KillSwitch(scope=scope, target=target, engaged=False)
        db.add(switch)
    switch.engaged = False
    switch.released_by = actor.id if actor else None
    switch.released_at = utcnow()
    db.flush()
    _mirror(scope, target, False)
    audit.record(
        db,
        action=AuditAction.KILL_SWITCH_RELEASED,
        actor_user_id=actor.id if actor else None,
        actor_email=actor.email if actor else None,
        actor_role=actor.staff_role if actor else None,
        target_type="kill_switch",
        target_id=f"{scope}:{target}",
        meta={"reason": reason},
    )
    log.warning("kill_switch_released", extra={"extra_fields": {"scope": scope, "target": target}})
    return switch


def state_for(db: Session, org_id: str, provider: str | None = None, user_id: str | None = None) -> dict:
    return {
        "global": is_engaged(db, KillScope.GLOBAL, GLOBAL_TARGET),
        "org": is_engaged(db, KillScope.ORG, org_id),
        "provider": is_engaged(db, KillScope.PROVIDER, provider) if provider else False,
        "user": is_engaged(db, KillScope.USER, user_id) if user_id else False,
        "file_flag": _file_flag_present(),
    }
