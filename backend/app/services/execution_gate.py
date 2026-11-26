"""The gate every venue-bound order passes before it reaches an adapter.

This module is deterministic and has no knowledge of strategies. It answers one question —
"is this organisation allowed to send this order to this venue right now?" — and returns every
check it ran so the trade detail view can show exactly what passed and what blocked.

Two execution scopes:

* ``demo`` — a venue demo account (Deriv VRTC…). No real money moves, so the platform live flag
  and the subscriber's live authorisation are not required, but the kill switches, the
  connection's trade permission, the account status and the risk engine still are.
* ``real`` — real money. Requires the process-wide live flag, an active live authorisation with
  a completed checklist, a live-capable plan, and every kill switch released.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import settings
from app.db.constants import Entitlement
from app.db.models import Connection, TradingPermission, User
from app.services import entitlements, kill_switch
from sqlalchemy.orm import Session

DEMO = "demo"
REAL = "real"


@dataclass
class GateResult:
    allowed: bool
    scope: str
    checks: list[dict] = field(default_factory=list)

    @property
    def reasons(self) -> list[str]:
        return [c["check"] for c in self.checks if not c["ok"]]

    @property
    def blocking_message(self) -> str:
        failed = [c for c in self.checks if not c["ok"]]
        if not failed:
            return ""
        return "; ".join(f"{c['check']}: {c['detail']}" for c in failed)

    def as_dict(self) -> dict:
        return {"allowed": self.allowed, "scope": self.scope, "checks": self.checks}


def account_scope(connection: Connection) -> str:
    """Real money only when the venue says the account is real. Unknown counts as real."""
    account_type = (connection.provider_account_type or "").lower()
    if account_type == "demo":
        return DEMO
    return REAL


def evaluate(db: Session, *, user: User, connection: Connection) -> GateResult:
    scope = account_scope(connection)
    checks: list[dict] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    org_suspended = bool(getattr(user, "org", None) and user.org.suspended)
    record("org_active", not org_suspended, "Organisation is suspended." if org_suspended else "")
    record("user_active", user.status == "active", f"User status is '{user.status}'.")
    record(
        "connection_active",
        connection.revoked_at is None and connection.status in ("connected", "pending"),
        f"Connection status is '{connection.status}'.",
    )
    record(
        "trade_permission",
        bool(connection.permissions.get("trade")),
        "This connection is read-only; enable trading on it first.",
    )
    record(
        "credentials_present",
        connection.environment != "paper",
        "Paper connections do not route to a venue.",
    )

    switches = kill_switch.state_for(db, user.org_id, provider=connection.provider, user_id=user.id)
    engaged = [name for name, on in switches.items() if on]
    record("kill_switch", not engaged, f"Engaged: {', '.join(engaged)}" if engaged else "")

    if scope == REAL:
        record(
            "platform_live_switch",
            settings.live_trading_enabled,
            "Live trading is disabled platform-wide.",
        )
        record(
            "plan_live_capable",
            entitlements.has_feature(db, user.org_id, Entitlement.LIVE_TRADING),
            "The current plan does not include live trading.",
        )
        permission: TradingPermission | None = (
            db.query(TradingPermission)
            .filter(TradingPermission.org_id == user.org_id, TradingPermission.status == "active")
            .order_by(TradingPermission.authorized_at.desc())
            .first()
        )
        record(
            "live_authorisation",
            bool(permission and permission.live_enabled),
            "Complete the live-trading authorisation checklist first.",
        )
        checklist = (permission.checklist or {}) if permission else {}
        record(
            "authorisation_checklist",
            bool(checklist) and all(checklist.values()),
            "The safety checklist is incomplete.",
        )
        record(
            "withdrawal_scope_absent",
            connection.permissions.get("withdrawal_scope") in (None, "not_requested", "disabled")
            or connection.permissions.get("withdraw") is False,
            "The venue credential has withdrawal scope.",
        )
    else:
        record("venue_demo_account", True, "Venue demo account: no real funds at risk.")

    return GateResult(allowed=all(c["ok"] for c in checks), scope=scope, checks=checks)
