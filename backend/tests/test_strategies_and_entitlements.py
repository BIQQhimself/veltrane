from __future__ import annotations

from tests.conftest import BASE


def test_free_plan_cannot_backtest(client, trader):
    response = client.post(
        f"{BASE}/backtests",
        json={"strategy_code": "trend_following_v1", "symbol": "BTC/USDT", "timeframe": "1h"},
        headers=trader["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "entitlement_required"

    me = client.get(f"{BASE}/auth/me", headers=trader["headers"]).json()
    assert me["entitlements"]["limits"]["backtesting"] is False


def test_strategy_library_is_plan_scoped(client, trader, pro_trader, elite_trader):
    free = client.get(f"{BASE}/strategies", headers=trader["headers"]).json()["strategies"]
    free_entitled = {s["code"] for s in free if s["entitled"]}
    assert free_entitled == {"trend_following_v1"}

    pro = client.get(f"{BASE}/strategies", headers=pro_trader["headers"]).json()["strategies"]
    pro_entitled = {s["code"] for s in pro if s["entitled"]}
    assert {"trend_following_v1", "mean_reversion_v1", "breakout_v1"}.issubset(pro_entitled)

    elite = client.get(f"{BASE}/strategies", headers=elite_trader["headers"]).json()["strategies"]
    elite_entitled = {s["code"] for s in elite if s["entitled"]}
    assert len(elite_entitled) > len(pro_entitled)

    # Every strategy must declare its limitations and methodology.
    for strategy in elite:
        assert strategy["known_limitations"]
        assert strategy["backtest_methodology"]
        assert strategy["entry_rules"]
        assert strategy["exit_rules"]
        assert strategy["data_requirements"]


def test_free_user_cannot_use_unentitled_strategy(client, trader):
    response = client.post(
        f"{BASE}/paper-sessions",
        json={"strategy_code": "breakout_v1", "symbol": "BTC/USDT", "timeframe": "1h"},
        headers=trader["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "entitlement_required"


def test_custom_strategy_version_requires_approval(client, pro_trader, trader):
    forbidden = client.post(
        f"{BASE}/strategies/trend_following_v1/versions",
        json={"params": {"fast_ema": 20}, "changelog": "tighter"},
        headers=trader["headers"],
    )
    assert forbidden.status_code == 403

    created = client.post(
        f"{BASE}/strategies/trend_following_v1/versions",
        json={"params": {"fast_ema": 20, "slow_ema": 80}, "changelog": "Tighter trend filter"},
        headers=pro_trader["headers"],
    )
    assert created.status_code == 201, created.text
    version = created.json()["version"]
    assert version["status"] == "draft"

    refused = client.post(
        f"{BASE}/strategies/versions/{version['id']}/approve",
        json={"acknowledge_risk": False},
        headers=pro_trader["headers"],
    )
    assert refused.status_code == 400

    approved = client.post(
        f"{BASE}/strategies/versions/{version['id']}/approve",
        json={"acknowledge_risk": True},
        headers=pro_trader["headers"],
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    out_of_range = client.post(
        f"{BASE}/strategies/trend_following_v1/versions",
        json={"params": {"fast_ema": 500}, "changelog": "invalid"},
        headers=pro_trader["headers"],
    )
    assert out_of_range.status_code in (400, 422)


def test_backtest_is_net_of_costs_and_reproducible(client, pro_trader):
    payload = {"strategy_code": "trend_following_v1", "symbol": "BTC/USDT", "timeframe": "1h"}
    first = client.post(f"{BASE}/backtests", json=payload, headers=pro_trader["headers"])
    assert first.status_code == 201, first.text
    body = first.json()
    metrics = body["metrics"]
    assert body["data_source"] == "demo"
    assert metrics["trades"] >= 0
    assert metrics["total_fees"] >= 0
    assert metrics["cost_model"]["fee_bps"] > 0
    assert "buy_hold_return_pct" in metrics
    assert "cost_drag_pct" in metrics
    assert body["equity_curve"]

    second = client.post(f"{BASE}/backtests", json=payload, headers=pro_trader["headers"])
    assert second.status_code == 201
    assert second.json()["metrics"]["final_equity"] == metrics["final_equity"]


def test_backtest_walk_forward(client, pro_trader):
    response = client.post(
        f"{BASE}/backtests",
        json={"strategy_code": "mean_reversion_v1", "symbol": "ETH/USDT", "timeframe": "1h", "walk_forward": True},
        headers=pro_trader["headers"],
    )
    assert response.status_code == 201, response.text
    metrics = response.json()["metrics"]
    assert "walk_forward" in metrics
    assert len(metrics["walk_forward"]["folds"]) >= 2


def test_backtest_daily_limit(client, pro_trader, db):
    from app.services import usage

    usage.increment_usage(db, pro_trader["org_id"], "backtests", 25)
    db.commit()
    response = client.post(
        f"{BASE}/backtests",
        json={"strategy_code": "trend_following_v1", "symbol": "BTC/USDT", "timeframe": "1h"},
        headers=pro_trader["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "backtest_limit_reached"


def test_paper_session_lifecycle(client, pro_trader):
    started = client.post(
        f"{BASE}/paper-sessions",
        json={"strategy_code": "trend_following_v1", "symbol": "BTC/USDT", "timeframe": "1h"},
        headers=pro_trader["headers"],
    )
    assert started.status_code == 201, started.text
    session = started.json()
    assert session["status"] == "running"
    assert session["is_demo"] is True

    duplicate = client.post(
        f"{BASE}/paper-sessions",
        json={"strategy_code": "trend_following_v1", "symbol": "BTC/USDT", "timeframe": "1h"},
        headers=pro_trader["headers"],
    )
    assert duplicate.status_code == 400
    assert duplicate.json()["detail"]["code"] == "session_running"

    tick = client.post(f"{BASE}/paper-sessions/{session['id']}/tick", headers=pro_trader["headers"])
    assert tick.status_code == 200, tick.text
    assert tick.json()["status"] == "ok"
    assert tick.json()["is_demo_feed"] is True

    detail = client.get(f"{BASE}/paper-sessions/{session['id']}", headers=pro_trader["headers"]).json()
    assert detail["session"]["last_tick_at"]
    assert "simulated" in detail["disclaimer"].lower()

    stopped = client.post(f"{BASE}/paper-sessions/{session['id']}/stop", headers=pro_trader["headers"])
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"


def test_entitlement_override_applies_server_side(client, trader, admin):
    before = client.get(f"{BASE}/auth/me", headers=trader["headers"]).json()["entitlements"]
    assert before["limits"]["backtesting"] is False

    override = client.post(
        f"{BASE}/admin/entitlements/override",
        json={"org_id": trader["org_id"], "key": "backtesting", "value": True, "reason": "support escalation"},
        headers=admin["headers"],
    )
    assert override.status_code == 201, override.text

    after = client.get(f"{BASE}/auth/me", headers=trader["headers"]).json()["entitlements"]
    assert after["limits"]["backtesting"] is True

    allowed = client.post(
        f"{BASE}/backtests",
        json={"strategy_code": "trend_following_v1", "symbol": "BTC/USDT", "timeframe": "1h"},
        headers=trader["headers"],
    )
    assert allowed.status_code == 201


def test_admin_can_change_prices_and_entitlements_follow_plan(client, trader, admin):
    update = client.patch(
        f"{BASE}/admin/plans/basic",
        json={"price_monthly": 24.0, "tagline": "Updated pricing"},
        headers=admin["headers"],
    )
    assert update.status_code == 200
    plans = client.get(f"{BASE}/plans").json()["plans"]
    basic = next(p for p in plans if p["code"] == "basic")
    assert basic["price_monthly"] == 24.0
    assert basic["tagline"] == "Updated pricing"
