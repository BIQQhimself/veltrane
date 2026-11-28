"""Plan rules for automated trading.

This module answers one question — may this tenant's automation act right now — and nothing
else. It never produces a signal, never prices a contract and never calls an adapter.
``autotrade.run_config`` asks it before it evaluates a strategy and turns a refusal into a halt
reason, so the runner keeps its normal loop and the existing strategy, signal and execution
code is untouched.

Modes
-----
``none``        no automation at all (Free).
``session``     automation only while the subscriber has the platform open (Tier 1).
``background``  automation continues while the browser is closed (Tier 2 and Elite).

The daily cap counts automated entries actually placed today. Elite carries no cap, but is
still subject to the venue, available funds and every deterministic risk rule.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.errors import forbidden
from app.db.constants import Entitlement
from app.db.models import AutoTradeSignal
from app.services import entitlements, presence
from sqlalchemy import func
from sqlalchemy.orm import Session

MODE_NONE = "none"
MODE_SESSION = "session"
MODE_BACKGROUND = "background"

MODE_LABELS = {
    MODE_NONE: "Automation not included",
    MODE_SESSION: "Runs while you are on the platform",
    MODE_BACKGROUND: "Runs in the background",
}


def _today_start() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def mode(db: Session, org_id: str) -> str:
    value = entitlements.limit_for(db, org_id, Entitlement.AUTOMATION_MODE, MODE_NONE)
    return value if value in MODE_LABELS else MODE_NONE


def daily_cap(db: Session, org_id: str) -> int | None:
    """Automated entries allowed today. ``None`` is uncapped (VIP, stored as -1).

    ``0`` is a plan that may not automate at all, not an uncapped one: the previous
    ``<= 0 -> None`` reading turned "no allowance" into "unlimited".
    """
    raw = entitlements.limit_for(db, org_id, Entitlement.MAX_AUTOMATED_TRADES_PER_DAY, 0)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return None if value < 0 else max(0, value)


def executions_today(db: Session, org_id: str) -> int:
    count = (
        db.query(func.count(AutoTradeSignal.id))
        .filter(
            AutoTradeSignal.org_id == org_id,
            AutoTradeSignal.status == "executed",
            AutoTradeSignal.created_at >= _today_start(),
        )
        .scalar()
    )
    return int(count or 0)


def state(db: Session, org_id: str) -> dict:
    current = mode(db, org_id)
    cap = daily_cap(db, org_id)
    used = executions_today(db, org_id)
    online = presence.is_online(org_id) if current != MODE_NONE else False
    remaining = None if cap is None else max(0, cap - used)

    blockers: list[str] = []
    if current == MODE_NONE:
        blockers.append("Your plan does not include automated trading.")
    elif current == MODE_SESSION and not online:
        blockers.append("Session automation runs only while the platform is open.")
    if remaining is not None and remaining <= 0:
        blockers.append("Today's automated-trade allowance is used up.")

    return {
        "mode": current,
        "label": MODE_LABELS[current],
        "runs_in_background": current == MODE_BACKGROUND,
        "session_online": online,
        "session_ttl_seconds": presence.PRESENCE_TTL_SECONDS,
        "daily_cap": cap,
        "used_today": used,
        "remaining_today": remaining,
        "allowed": not blockers,
        "blockers": blockers,
    }


def blocking_reason(db: Session, org_id: str) -> str:
    """One sentence for the runner's halt reason, or an empty string when automation may act."""
    snapshot = state(db, org_id)
    if snapshot["mode"] == MODE_NONE:
        return "Automated trading is not included in this plan."
    if snapshot["mode"] == MODE_SESSION and not snapshot["session_online"]:
        return "Session automation paused: the platform is closed."
    if snapshot["remaining_today"] is not None and snapshot["remaining_today"] <= 0:
        return f"Daily automated-trade allowance reached ({snapshot['daily_cap']})."
    return ""


def require_plan(db: Session, org_id: str) -> None:
    """Refuse to switch automation on for a plan that does not include it."""
    if mode(db, org_id) == MODE_NONE:
        raise forbidden(
            "automation_plan_required",
            "Automated trading is not included in your plan. Upgrade to Tier 1 or above to run strategies.",
        )
