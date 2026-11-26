"""Two-key master switch for platform-wide live trading.

The deployment flag (``VELTRANE_LIVE_TRADING_ENABLED``) belongs to whoever operates the
host. The staff key stored here belongs to the Owner/Admin inside the application. Live
execution requires both, so neither an operator alone nor a logged-in administrator alone
can put real money at risk. A missing staff row leaves the staff key at its safe default,
which keeps the deployment flag as the only authority until somebody deliberately uses
the switch.

Only the staff key is writable at runtime; the deployment flag is read from the
environment on every call so an operator can always stop live trading without the app.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import settings
from app.db.constants import AuditAction
from app.db.models import SystemSetting, User
from app.services import audit
from sqlalchemy.orm import Session

SETTING_KEY = "live_trading.staff_control"


def _row(db: Session) -> SystemSetting | None:
    return db.get(SystemSetting, SETTING_KEY)


def staff_enabled(db: Session) -> bool:
    row = _row(db)
    if row is None:
        return True
    return bool(row.value.get("enabled", True))


def effective(db: Session) -> bool:
    """Live trading is possible only when the deployment flag and the staff key agree."""
    return bool(settings.live_trading_enabled) and staff_enabled(db)


def state(db: Session) -> dict:
    row = _row(db)
    value = row.value if row is not None else {}
    return {
        "deployment_enabled": bool(settings.live_trading_enabled),
        "staff_enabled": staff_enabled(db),
        "effective": effective(db),
        "reason": value.get("reason", ""),
        "updated_at": value.get("updated_at"),
        "updated_by": value.get("updated_by"),
        "note": (
            "Live execution needs both keys. The deployment flag is set by the operator in the "
            "host environment; this switch is the in-app Owner/Admin key."
        ),
    }


def set_staff(db: Session, *, user: User, enabled: bool, reason: str) -> dict:
    row = _row(db)
    payload = {
        "enabled": bool(enabled),
        "reason": reason.strip(),
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by": user.email,
    }
    if row is None:
        row = SystemSetting(
            key=SETTING_KEY,
            value=payload,
            description="Owner/Admin key for platform-wide live trading",
            updated_by=user.id,
        )
        db.add(row)
    else:
        row.value = payload
        row.updated_by = user.id
    audit.record(
        db,
        action=AuditAction.LIVE_SWITCH_CHANGED,
        org_id=user.org_id,
        actor_user_id=user.id,
        target_type="system_setting",
        target_id=SETTING_KEY,
        meta={
            "staff_enabled": bool(enabled),
            "deployment_enabled": bool(settings.live_trading_enabled),
            "reason": reason.strip(),
        },
    )
    db.commit()
    return state(db)
