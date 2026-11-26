from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models import Order, PaperSession
from app.services import scheduler

BASE = "/api/v1"


def _start_session(client, account, *, symbol="BTC/USDT", timeframe="1h") -> dict:
    created = client.post(
        f"{BASE}/paper-sessions",
        json={"strategy_code": "trend_following_v1", "symbol": symbol, "timeframe": timeframe},
        headers=account["headers"],
    )
    assert created.status_code == 201, created.text
    return created.json()


def _age_session(db, session_id: str, *, minutes: int) -> None:
    row = db.get(PaperSession, session_id)
    row.last_tick_at = datetime.now(UTC) - timedelta(minutes=minutes)
    db.commit()


def test_scheduler_ticks_a_due_session(client, db, pro_trader):
    session = _start_session(client, pro_trader)
    _age_session(db, session["id"], minutes=5)

    summary = scheduler.tick_due_sessions(db, interval_seconds=60)

    assert summary["ticked"] >= 1
    refreshed = db.get(PaperSession, session["id"])
    db.refresh(refreshed)
    assert refreshed.last_tick_at is not None
    assert refreshed.last_tick_at > datetime.now(UTC) - timedelta(minutes=1)


def test_scheduler_skips_a_fresh_session(client, db, pro_trader):
    session = _start_session(client, pro_trader)
    client.post(f"{BASE}/paper-sessions/{session['id']}/tick", headers=pro_trader["headers"])

    due_ids = {s.id for s in scheduler.due_sessions(db, interval_seconds=600)}
    assert session["id"] not in due_ids


def test_scheduler_ignores_stopped_and_strategy_less_sessions(client, db, pro_trader):
    stopped = _start_session(client, pro_trader)
    client.post(f"{BASE}/paper-sessions/{stopped['id']}/stop", headers=pro_trader["headers"])
    _age_session(db, stopped["id"], minutes=30)

    provisioned = client.post(f"{BASE}/trading/paper-session", headers=pro_trader["headers"]).json()

    due_ids = {s.id for s in scheduler.due_sessions(db, interval_seconds=60)}
    assert stopped["id"] not in due_ids
    assert provisioned["id"] not in due_ids


def test_scheduler_only_ever_submits_paper_orders(client, db, pro_trader):
    session = _start_session(client, pro_trader)
    _age_session(db, session["id"], minutes=5)
    before = db.query(Order).count()

    scheduler.tick_due_sessions(db, interval_seconds=60)

    for order in db.query(Order).offset(before).all():
        assert order.mode == "paper"
        assert order.is_demo is True


def test_a_broken_session_does_not_stop_the_runner(client, db, pro_trader):
    healthy = _start_session(client, pro_trader, symbol="BTC/USDT")
    _age_session(db, healthy["id"], minutes=5)

    row = db.get(PaperSession, healthy["id"])
    # A second row in the same org pointing at an instrument the feed does not carry.
    # Created directly because the service allows one running session per org.
    broken = PaperSession(
        org_id=row.org_id,
        strategy_version_id=row.strategy_version_id,
        instrument_symbol="ZZZ/ZZZ",
        timeframe="1h",
        status="running",
        starting_balance=25000,
        cash_balance=25000,
        equity=25000,
        config={},
        last_tick_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(broken)
    db.commit()

    summary = scheduler.tick_due_sessions(db, interval_seconds=60)

    assert summary["errors"] == 1
    assert summary["ticked"] >= 1
    refreshed = db.get(PaperSession, healthy["id"])
    db.refresh(refreshed)
    assert refreshed.last_tick_at > datetime.now(UTC) - timedelta(minutes=1)


def test_scheduler_state_is_reportable(client, db, pro_trader):
    state = scheduler.scheduler_state()
    assert {
        "running",
        "interval_seconds",
        "last_run_at",
        "last_summary",
        "last_error",
        "deriv_last_run_at",
        "deriv_last_summary",
        "deriv_last_error",
        "email_last_run_at",
        "email_last_summary",
        "email_last_error",
    } == set(state)
