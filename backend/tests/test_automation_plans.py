"""Plan rules for automated trading, session presence and the daily automated cap."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models import AutoTradeConfig, AutoTradeSignal, Connection, Plan, User
from app.services import automation_limits, entitlements, presence

BASE = "/api/v1"


def _subscribe(client, account, plan_code: str) -> dict:
    checkout = client.post(f"{BASE}/billing/checkout", json={"plan_code": plan_code}, headers=account["headers"])
    assert checkout.status_code == 200, checkout.text
    done = client.post(
        f"{BASE}/billing/mock/complete",
        json={"checkout_token": checkout.json()["checkout_token"]},
        headers=account["headers"],
    )
    assert done.status_code == 200, done.text
    me = client.get(f"{BASE}/auth/me", headers=account["headers"])
    assert me.status_code == 200, me.text
    return me.json()


def _connection(db, account, provider: str = "deriv") -> Connection:
    row = Connection(
        org_id=account["org_id"],
        created_by=account["user_id"],
        kind="broker",
        provider=provider,
        label=f"{provider}-{account['org_id'][:6]}",
        environment="demo",
        status="connected",
        provider_account_type="demo",
    )
    db.add(row)
    db.commit()
    return row


def test_free_plan_has_no_automation(client, trader, db):
    state = client.get(f"{BASE}/presence", headers=trader["headers"]).json()["automation"]
    assert state["mode"] == "none"
    assert state["allowed"] is False
    assert state["daily_cap"] == 0 or state["daily_cap"] is None
    assert "does not include" in state["blockers"][0]

    connection = _connection(db, trader)
    response = client.put(
        f"{BASE}/deriv/connections/{connection.id}/automation",
        json={"enabled": True, "mode": "autonomous"},
        headers=trader["headers"],
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "automation_plan_required"


def test_tier_one_automation_is_session_bound(client, trader, db):
    body = _subscribe(client, trader, "basic")
    assert body["automation"]["mode"] == "session"
    assert body["automation"]["session_online"] is False

    # Offline: session automation must refuse, and say why.
    offline = client.get(f"{BASE}/presence", headers=trader["headers"]).json()["automation"]
    assert offline["allowed"] is False
    assert "platform is open" in offline["blockers"][0]
    assert automation_limits.blocking_reason(db, trader["org_id"]).startswith("Session automation paused")

    # A heartbeat opens the session.
    beat = client.post(f"{BASE}/presence/heartbeat", headers=trader["headers"])
    assert beat.status_code == 200, beat.text
    online = beat.json()["automation"]
    assert online["session_online"] is True
    assert online["allowed"] is True
    assert automation_limits.blocking_reason(db, trader["org_id"]) == ""

    # Leaving the platform closes it again.
    assert client.delete(f"{BASE}/presence", headers=trader["headers"]).status_code == 200
    assert presence.is_online(trader["org_id"]) is False


def test_tier_two_runs_without_a_session(client, trader, db):
    body = _subscribe(client, trader, "pro")
    assert body["automation"]["mode"] == "background"
    assert body["automation"]["runs_in_background"] is True
    assert body["automation"]["session_online"] is False
    assert body["automation"]["allowed"] is True
    assert automation_limits.blocking_reason(db, trader["org_id"]) == ""


def test_elite_is_capped_and_vip_is_uncapped(client, trader, db):
    """Elite carries 2,400 trades a day; only VIP is uncapped, and the venue still bounds it."""
    elite = _subscribe(client, trader, "elite")
    assert elite["automation"]["daily_cap"] == 2400
    assert elite["automation"]["remaining_today"] == 2400
    assert elite["automation"]["allowed"] is True

    vip = _subscribe(client, trader, "vip")
    assert vip["automation"]["daily_cap"] is None
    assert vip["automation"]["remaining_today"] is None
    assert vip["automation"]["allowed"] is True


def test_every_plan_matches_the_published_allowance(db):
    # Owner-approved matrix: Free cannot execute; VIP is stored as -1 (uncapped).
    expected = {"free": 0, "basic": 600, "pro": 1200, "elite": 2400, "vip": -1}
    plans = {plan.code: plan for plan in db.query(Plan).all()}
    for code, allowance in expected.items():
        assert plans[code].limits["max_daily_executions"] == allowance, code
    assert set(expected) <= set(plans)


def test_daily_automated_cap_counts_executed_signals(client, trader, db):
    _subscribe(client, trader, "basic")
    client.post(f"{BASE}/presence/heartbeat", headers=trader["headers"])
    connection = _connection(db, trader)
    user = db.get(User, trader["user_id"])
    cap = automation_limits.daily_cap(db, trader["org_id"])
    assert cap and cap > 0

    for _ in range(cap):
        db.add(
            AutoTradeSignal(
                org_id=trader["org_id"],
                connection_id=connection.id,
                status="executed",
                mode="autonomous",
                symbol="R_100",
                side="buy",
                contract_type="CALL",
                stake=10,
                duration=5,
                duration_unit="t",
                reason="test",
            )
        )
    # A pending signal is not a trade; it must not consume the allowance.
    db.add(
        AutoTradeSignal(
            org_id=trader["org_id"],
            connection_id=connection.id,
            status="pending",
            mode="approval",
            symbol="R_100",
            side="buy",
            contract_type="CALL",
            stake=10,
            duration=5,
            duration_unit="t",
            reason="test",
        )
    )
    db.commit()

    state = automation_limits.state(db, trader["org_id"])
    assert state["used_today"] == cap
    assert state["remaining_today"] == 0
    assert state["allowed"] is False
    assert "allowance" in automation_limits.blocking_reason(db, trader["org_id"])
    assert db.query(User).filter(User.id == user.id).count() == 1


def test_yesterdays_signals_do_not_count(client, trader, db):
    _subscribe(client, trader, "basic")
    connection = _connection(db, trader)
    signal = AutoTradeSignal(
        org_id=trader["org_id"],
        connection_id=connection.id,
        status="executed",
        mode="autonomous",
        symbol="R_100",
        side="buy",
        contract_type="CALL",
        stake=10,
        duration=5,
        duration_unit="t",
        reason="test",
    )
    db.add(signal)
    db.commit()
    signal.created_at = datetime.now(UTC) - timedelta(days=1)
    db.commit()
    assert automation_limits.executions_today(db, trader["org_id"]) == 0


def test_runner_halts_session_automation_when_the_platform_is_closed(client, trader, db, monkeypatch):
    from app.services import autotrade

    _subscribe(client, trader, "basic")
    connection = _connection(db, trader)
    config = AutoTradeConfig(
        org_id=trader["org_id"],
        connection_id=connection.id,
        enabled=True,
        mode="autonomous",
        created_by=trader["user_id"],
    )
    db.add(config)
    db.commit()

    result = autotrade.run_config(db, config)
    assert "Session automation paused" in result["skipped"]
    assert "Session automation paused" in (config.halt_reason or "")

    # With the platform open the runner proceeds to the execution gate instead of the plan gate.
    client.post(f"{BASE}/presence/heartbeat", headers=trader["headers"])
    result = autotrade.run_config(db, config)
    assert "Session automation paused" not in str(result)


def test_plan_defaults_fill_missing_stored_limits(client, trader, db):
    """A plan row written before a limit existed must still answer with the catalogue default."""
    plan = db.get(Plan, "basic")
    limits = dict(plan.limits)
    limits.pop("automation_mode")
    limits.pop("max_automated_trades_per_day")
    plan.limits = limits
    db.commit()

    resolved = entitlements.resolve_entitlements(db, trader["org_id"])
    # The tenant is on Free; check the Basic catalogue row through the stored-plan path.
    assert resolved["plan_code"] == "free"
    assert entitlements.PLAN_CATALOG[1]["limits"]["automation_mode"] == "session"
    assert entitlements.PLAN_CATALOG[1]["limits"]["max_automated_trades_per_day"] > 0
