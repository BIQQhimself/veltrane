"""Paper-session scheduler.

Autonomous paper trading: running paper sessions are ticked on a fixed cadence so a
strategy keeps evaluating new candles without a human pressing a button.

There is no path from this module to live execution. It only calls ``run_paper_tick``,
which submits ``mode="paper"`` orders, and those still pass the deterministic risk
engine exactly like an order typed by hand. A session started without a strategy
version has nothing to evaluate and is never ticked.
"""
from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.db.models import PaperSession, User
from app.db.session import SessionLocal
from sqlalchemy.orm import Session

log = logging.getLogger("veltrane.scheduler")

_state: dict[str, object] = {
    "running": False,
    "interval_seconds": 0,
    "last_run_at": None,
    "last_summary": None,
    "last_error": None,
}

# Sessions already reported as failing, so a broken row does not log every minute.
_warned: set[str] = set()


def scheduler_state() -> dict:
    return dict(_state)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def due_sessions(
    db: Session, *, now: datetime | None = None, interval_seconds: int | None = None
) -> list[PaperSession]:
    """Running, strategy-backed sessions whose last tick is older than the interval."""
    now = now or _utcnow()
    interval = timedelta(seconds=interval_seconds or settings.scheduler_interval_seconds)
    cutoff = now - interval
    rows = (
        db.query(PaperSession)
        .filter(PaperSession.status == "running", PaperSession.strategy_version_id.isnot(None))
        .all()
    )
    return [s for s in rows if s.last_tick_at is None or _as_utc(s.last_tick_at) <= cutoff]


def tick_due_sessions(
    db: Session, *, now: datetime | None = None, interval_seconds: int | None = None
) -> dict:
    """Tick every due session once. One failing session never stops the others."""
    from app.services import strategy_service

    due = due_sessions(db, now=now, interval_seconds=interval_seconds)
    summary = {"due": len(due), "ticked": 0, "actions": 0, "errors": 0}
    for session in due:
        user = db.query(User).filter(User.org_id == session.org_id).order_by(User.created_at).first()
        if user is None:
            log.warning(
                "paper_tick_no_owner",
                extra={"extra_fields": {"session_id": session.id, "org_id": session.org_id}},
            )
            continue
        try:
            result = strategy_service.run_paper_tick(db, user=user, session=session)
            summary["ticked"] += 1
            summary["actions"] += len(result.get("actions") or [])
            _warned.discard(session.id)
        except Exception as exc:
            db.rollback()
            summary["errors"] += 1
            if session.id not in _warned:
                _warned.add(session.id)
                log.warning(
                    "paper_tick_failed",
                    extra={
                        "extra_fields": {
                            "session_id": session.id,
                            "org_id": session.org_id,
                            "error": type(exc).__name__,
                            "detail": str(exc)[:200],
                        }
                    },
                )
    return summary


class SessionScheduler:
    """Daemon thread that ticks due paper sessions every ``interval_seconds``."""

    def __init__(self, interval_seconds: int | None = None):
        self.interval_seconds = int(interval_seconds or settings.scheduler_interval_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        _state.update(running=True, interval_seconds=self.interval_seconds, last_error=None)
        self._thread = threading.Thread(target=self._loop, name="veltrane-paper-scheduler", daemon=True)
        self._thread.start()
        log.info("scheduler_started", extra={"extra_fields": {"interval_seconds": self.interval_seconds}})

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        _state["running"] = False
        log.info("scheduler_stopped")

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.run_once()

    def run_once(self) -> dict:
        db = SessionLocal()
        try:
            summary = tick_due_sessions(db)
            _state.update(last_run_at=_utcnow().isoformat(), last_summary=summary, last_error=None)
            if summary["ticked"] or summary["errors"]:
                log.info("scheduler_tick", extra={"extra_fields": summary})
            return summary
        except Exception as exc:
            _state["last_error"] = type(exc).__name__
            log.exception("scheduler_tick_failed")
            return {"due": 0, "ticked": 0, "actions": 0, "errors": 1, "error": type(exc).__name__}
        finally:
            db.close()
