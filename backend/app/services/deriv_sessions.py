"""Process-wide registry of Deriv trading sessions.

One OTP-authenticated socket per connection, owned by the API process. The socket survives
between requests; when it drops, ``DerivTradingSession`` pauses trading until ``resume_checks``
re-verifies the account and reconciles open contracts.

The platform runs a single API process (documented in AGENTS.md) so this in-process registry is
the single owner of each session. A multi-process deployment needs a shared session broker before
it can run autonomous venue trading — recorded in KNOWN_LIMITATIONS.md.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

from app.core.config import settings
from app.db.models import Connection, ProviderAuthEvent
from app.providers.base import CredentialBundle, ProviderError
from app.providers.deriv import DerivProvider, build_deriv_provider
from app.providers.deriv_client import DerivREST, DerivTradingSession
from app.services import execution_gate
from app.services.connections import load_credentials
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

_lock = threading.Lock()
_sessions: dict[str, DerivTradingSession] = {}
_symbols: dict[str, object] = {"at": None, "map": {}}
SYMBOL_TTL_SECONDS = 300


def _utcnow() -> datetime:
    return datetime.now(UTC)


def adapter() -> DerivProvider:
    return build_deriv_provider()


def venue_symbol_map() -> dict[str, dict]:
    """Deriv's active symbol catalogue, cached. Empty on failure: the caller must not assume."""
    cached_at = _symbols["at"]
    if isinstance(cached_at, datetime) and (_utcnow() - cached_at).total_seconds() < SYMBOL_TTL_SECONDS:
        return _symbols["map"]  # type: ignore[return-value]
    try:
        rows = adapter().active_symbols()
    except Exception:  # noqa: BLE001 - a catalogue outage must not break execution gating
        log.warning("deriv_symbol_catalogue_unavailable")
        return {}
    mapping = {row["underlying_symbol"]: row for row in rows if row.get("underlying_symbol")}
    _symbols["map"] = mapping
    _symbols["at"] = _utcnow()
    return mapping


def reset_symbol_cache() -> None:
    _symbols["at"] = None
    _symbols["map"] = {}


def record_auth_event(
    db: Session,
    *,
    connection: Connection | None,
    org_id: str | None,
    event: str,
    outcome: str,
    code: str | None = None,
    message: str | None = None,
    detail: dict | None = None,
) -> None:
    """Persist an authentication/session event. Never stores token material."""
    db.add(
        ProviderAuthEvent(
            org_id=org_id or (connection.org_id if connection else None),
            connection_id=connection.id if connection else None,
            provider="deriv",
            event=event,
            outcome=outcome,
            code=(code or "")[:64] or None,
            message=(message or "")[:2000] or None,
            detail=detail or {},
            occurred_at=_utcnow(),
        )
    )
    if connection is not None:
        if outcome == "failed":
            connection.last_auth_error = (message or code or "")[:1000]
            connection.last_auth_error_at = _utcnow()
        else:
            connection.last_auth_error = None
            connection.last_auth_error_at = None
    db.flush()


def _build(connection: Connection, credentials: CredentialBundle) -> DerivTradingSession:
    rest = DerivREST(
        credentials.api_key,
        app_id=credentials.app_id or settings.deriv_app_id,
        base_url=settings.deriv_rest_base,
        token_kind="oauth" if credentials.app_id == "__oauth__" else "pat",
    )
    return DerivTradingSession(
        rest=rest,
        account_id=connection.provider_account_id or credentials.account_id,
        account_type=connection.provider_account_type or "",
        currency=connection.provider_currency or "",
        max_consecutive_failures=settings.deriv_session_max_failures,
    )


def get_session(connection_id: str) -> DerivTradingSession | None:
    with _lock:
        return _sessions.get(connection_id)


def session_for(db: Session, connection: Connection, *, allowed: bool) -> DerivTradingSession:
    """Return a connected, safety-checked session or raise ``ProviderError``."""
    if connection.provider != "deriv":
        raise ProviderError("not_deriv", "This connection is not a Deriv connection.")
    if not connection.provider_account_id:
        raise ProviderError(
            "account_not_selected",
            "Re-save this connection and choose the Deriv account to trade.",
        )

    with _lock:
        session = _sessions.get(connection.id)

    if session is not None and session.state.suspended:
        raise ProviderError(
            "session_suspended",
            f"The Deriv session is suspended: {session.state.suspension_reason or 'safety stop'}.",
        )

    if session is None or not session.connected:
        credentials = load_credentials(db, connection)
        session = _build(connection, credentials)
        try:
            session.connect()
            record_auth_event(
                db,
                connection=connection,
                org_id=connection.org_id,
                event="session_connected",
                outcome="ok",
                detail={"account_id": session.account_id},
            )
        except ProviderError:
            session.close()
            raise
        except Exception as exc:  # noqa: BLE001 - provider errors are the only expected kind
            session.close()
            record_auth_event(
                db,
                connection=connection,
                org_id=connection.org_id,
                event="session_connect_failed",
                outcome="failed",
                code=type(exc).__name__,
                message=str(exc),
            )
            raise ProviderError("session_failed", "Could not open a Deriv trading session.") from exc
        with _lock:
            _sessions[connection.id] = session

    checks = session.resume_checks(allowed=allowed)
    connection.session_state = session.as_dict()
    if not checks["resumed"]:
        record_auth_event(
            db,
            connection=connection,
            org_id=connection.org_id,
            event="session_checks_failed",
            outcome="failed",
            code="safety_checks_failed",
            message="; ".join(c["check"] for c in checks["checks"] if not c["ok"]),
            detail={"checks": checks["checks"]},
        )
        raise ProviderError(
            "session_not_ready",
            "The Deriv session failed its safety checks: "
            + ", ".join(c["check"] for c in checks["checks"] if not c["ok"]),
        )
    db.flush()
    return session


def reconnect(db: Session, connection: Connection, *, allowed: bool) -> dict:
    session = get_session(connection.id)
    if session is None:
        session = session_for(db, connection, allowed=allowed)
        return session.as_dict()
    try:
        session.reconnect()
        record_auth_event(
            db,
            connection=connection,
            org_id=connection.org_id,
            event="session_reconnected",
            outcome="ok",
            detail={"reconnects": session.state.reconnects},
        )
    except ProviderError:
        raise
    except Exception as exc:  # noqa: BLE001
        record_auth_event(
            db,
            connection=connection,
            org_id=connection.org_id,
            event="session_reconnect_failed",
            outcome="failed",
            code=type(exc).__name__,
            message=str(exc),
        )
        raise ProviderError("reconnect_failed", "Could not reconnect the Deriv session.") from exc
    checks = session.resume_checks(allowed=allowed)
    connection.session_state = session.as_dict()
    db.flush()
    return {**session.as_dict(), "checks": checks["checks"]}


def close_session(connection_id: str) -> None:
    with _lock:
        session = _sessions.pop(connection_id, None)
    if session is not None:
        session.close()


def close_all() -> None:
    with _lock:
        sessions = list(_sessions.values())
        _sessions.clear()
    for session in sessions:
        try:
            session.close()
        except Exception:  # noqa: BLE001 - shutdown must not raise
            log.warning("deriv_session_close_failed")


def gate_for(db: Session, connection: Connection, user) -> execution_gate.GateResult:
    return execution_gate.evaluate(db, user=user, connection=connection)
