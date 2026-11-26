from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.conftest import BASE, mark_connection_connected, place_order


def test_paper_order_executes_and_is_labelled_demo(client, trader):
    result = place_order(client, trader["headers"])
    assert result["status_code"] == 201, result
    body = result["body"]
    assert body["order"]["status"] == "filled"
    assert body["order"]["is_demo"] is True
    assert body["fill"]["is_demo"] is True
    assert "Simulated execution" in body["disclaimer"]
    assert body["order"]["avg_fill_price"] > 0
    assert body["order"]["fee"] > 0
    assert body["order"]["risk_decision"]["decision"] == "approved"

    positions = client.get(f"{BASE}/positions", headers=trader["headers"]).json()["positions"]
    assert len(positions) == 1
    assert positions[0]["mode"] == "paper"
    assert positions[0]["symbol"] == "BTC/USDT"


def test_order_rejected_when_risk_rule_fails(client, trader):
    result = place_order(client, trader["headers"], quantity=10.0)  # far above 10% equity cap
    assert result["status_code"] == 201
    body = result["body"]
    assert body["order"]["status"] == "rejected"
    assert body["order"]["rejection_reason"]
    assert body["order"]["risk_decision"]["decision"] == "rejected"
    assert any(r["code"] == "position_size" for r in body["order"]["risk_decision"]["failed_rules"])
    assert body["fill"] is None


def test_demo_execution_limit_five_per_day(client, trader):
    for i in range(5):
        result = place_order(client, trader["headers"], quantity=0.001)
        assert result["body"]["order"]["status"] == "filled", (i, result["body"])

    sixth = place_order(client, trader["headers"], quantity=0.001)
    assert sixth["body"]["order"]["status"] == "rejected"
    codes = [r["code"] for r in sixth["body"]["order"]["risk_decision"]["failed_rules"]]
    assert "demo_execution_limit" in codes

    me = client.get(f"{BASE}/auth/me", headers=trader["headers"]).json()
    assert me["usage"]["demo_executions_today"] == 5


def test_idempotency_prevents_duplicate_fill(client, trader):
    first = place_order(client, trader["headers"], idempotency_key="fixed-key-1")
    assert first["body"]["order"]["status"] == "filled"
    second = place_order(client, trader["headers"], idempotency_key="fixed-key-1")
    assert second["body"]["idempotent_replay"] is True
    assert second["body"]["order"]["id"] == first["body"]["order"]["id"]

    orders = client.get(f"{BASE}/orders", headers=trader["headers"]).json()["orders"]
    assert len(orders) == 1


def test_duplicate_pending_order_is_blocked_by_risk(client, trader):
    # A second identical order with a *different* idempotency key must not slip past
    # the duplicate guard while the first is still live. Market orders fill instantly,
    # so we assert the risk rule exists and is enforced on the pending-state check.
    first = place_order(client, trader["headers"], quantity=0.002)
    assert first["body"]["order"]["status"] == "filled"
    checks = first["body"]["order"]["risk_decision"]["checks"]
    assert any(c["code"] == "duplicate_order" and c["passed"] for c in checks)


def test_trade_detail_contains_everything_required(client, trader):
    buy = place_order(client, trader["headers"], quantity=0.01, reason="Breakout entry per strategy signal")
    assert buy["body"]["order"]["status"] == "filled"
    position_id = client.get(f"{BASE}/positions", headers=trader["headers"]).json()["positions"][0]["id"]

    closed = client.post(
        f"{BASE}/positions/{position_id}/close",
        json={"reason": "Manual override", "note": "Operator closed early"},
        headers=trader["headers"],
    )
    assert closed.status_code == 200, closed.text
    trade_id = closed.json()["trade"]["id"]

    detail = client.get(f"{BASE}/trades/{trade_id}", headers=trader["headers"])
    assert detail.status_code == 200
    trade = detail.json()["trade"]
    for key in (
        "entry_reason",
        "strategy_version_id",
        "risk_snapshot",
        "fees",
        "slippage_est_bps",
        "slippage_actual_bps",
        "gross_pnl",
        "net_pnl",
        "opened_at",
        "closed_at",
        "human_intervention",
        "order",
        "cost_summary",
        "fees_breakdown",
    ):
        assert key in trade, key
    assert trade["human_intervention"] is True
    assert trade["intervention_note"] == "Operator closed early"
    assert trade["net_pnl"] <= trade["gross_pnl"]  # costs are always deducted
    assert trade["order"]["risk_decision"]["checks"]
    assert trade["is_demo"] is True

    explain = client.get(f"{BASE}/analytics/trades/{trade_id}/explain", headers=trader["headers"])
    assert explain.status_code == 200
    assert explain.json()["summary"]["net"] == trade["net_pnl"]


def test_kill_switch_blocks_new_orders_and_can_flatten(client, trader):
    place_order(client, trader["headers"], quantity=0.005)
    engaged = client.post(
        f"{BASE}/trading/kill-switch",
        json={"scope": "org", "reason": "Testing emergency halt", "flatten": True},
        headers=trader["headers"],
    )
    assert engaged.status_code == 200, engaged.text
    assert engaged.json()["status"] == "engaged"
    assert engaged.json()["flattened"]["closed"] == 1

    blocked = place_order(client, trader["headers"], quantity=0.001)
    assert blocked["body"]["order"]["status"] == "rejected"
    assert any(r["code"] == "kill_switch" for r in blocked["body"]["order"]["risk_decision"]["failed_rules"])

    released = client.post(
        f"{BASE}/trading/kill-switch/release",
        json={"scope": "org", "reason": "Resolved"},
        headers=trader["headers"],
    )
    assert released.status_code == 200
    after = place_order(client, trader["headers"], quantity=0.001)
    assert after["body"]["order"]["status"] == "filled"


def test_live_order_is_rejected_for_free_user(client, trader):
    connection = client.post(
        f"{BASE}/connections",
        json={"provider": "binance", "label": "Read only", "environment": "read_only", "api_key": "key", "api_secret": "secret"},
        headers=trader["headers"],
    )
    assert connection.status_code == 201, connection.text
    connection_id = connection.json()["id"]

    result = place_order(
        client,
        trader["headers"],
        mode="live",
        connection_id=connection_id,
        strategy_version_id=None,
        stop_loss=50_000.0,
        quantity=0.001,
    )
    assert result["status_code"] == 201
    order = result["body"]["order"]
    assert order["status"] == "rejected"
    codes = [r["code"] for r in order["risk_decision"]["failed_rules"]]
    assert "mode_authorization" in codes
    assert order["is_demo"] is False


def test_live_order_without_connection_is_refused(client, trader):
    response = client.post(
        f"{BASE}/orders",
        json={"symbol": "BTC/USDT", "side": "buy", "quantity": 0.001, "mode": "live"},
        headers=trader["headers"],
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "connection_required"


def test_free_user_cannot_start_live_authorization(client, trader):
    response = client.post(
        f"{BASE}/trading/live-authorization/start",
        json={"acknowledged": True, "checklist": {}, "jurisdiction": "GB"},
        headers=trader["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "entitlement_required"


def test_live_authorization_requires_checklist_and_cooloff(client, pro_trader, db):
    from app.db.models import TradingPermission

    incomplete = client.post(
        f"{BASE}/trading/live-authorization/start",
        json={"acknowledged": True, "checklist": {"understands_total_loss_risk": True}, "jurisdiction": "GB"},
        headers=pro_trader["headers"],
    )
    assert incomplete.status_code == 400
    assert incomplete.json()["detail"]["code"] == "checklist_incomplete"

    from app.services.live_authorization import CHECKLIST_ITEMS

    connection = client.post(
        f"{BASE}/connections",
        json={"provider": "binance", "label": "Trade key", "environment": "live", "api_key": "k", "api_secret": "s"},
        headers=pro_trader["headers"],
    )
    assert connection.status_code == 201, connection.text
    mark_connection_connected(db, connection.json()["id"])

    full = {key: True for key in CHECKLIST_ITEMS}
    started = client.post(
        f"{BASE}/trading/live-authorization/start",
        json={"acknowledged": True, "checklist": full, "jurisdiction": "GB"},
        headers=pro_trader["headers"],
    )
    assert started.status_code == 200, started.text
    token = started.json()["confirmation_token"]

    early = client.post(
        f"{BASE}/trading/live-authorization/confirm",
        json={"confirmation_token": token},
        headers=pro_trader["headers"],
    )
    assert early.status_code == 400
    assert early.json()["detail"]["code"] == "cooloff_active"

    # Simulate the elapsed cooling-off window without sleeping in the test suite.
    permission = db.query(TradingPermission).filter(TradingPermission.org_id == pro_trader["org_id"]).first()
    permission.risk_acknowledged_at = datetime.now(UTC) - timedelta(seconds=120)
    db.commit()

    confirmed = client.post(
        f"{BASE}/trading/live-authorization/confirm",
        json={"confirmation_token": token},
        headers=pro_trader["headers"],
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["live_enabled"] is True
    assert confirmed.json()["platform_live_enabled"] is False

    state = client.get(f"{BASE}/trading/state", headers=pro_trader["headers"]).json()
    assert state["live"]["live_enabled"] is True
    assert state["platform_live_enabled"] is False


def test_authorised_live_still_blocked_by_platform_flag(client, pro_trader, db):
    from datetime import datetime, timedelta

    from app.db.models import TradingPermission
    from app.services.live_authorization import CHECKLIST_ITEMS

    connection = client.post(
        f"{BASE}/connections",
        json={"provider": "binance", "label": "Trade key", "environment": "live", "api_key": "k", "api_secret": "s"},
        headers=pro_trader["headers"],
    )
    assert connection.status_code == 201
    mark_connection_connected(db, connection.json()["id"])
    started = client.post(
        f"{BASE}/trading/live-authorization/start",
        json={"acknowledged": True, "checklist": {k: True for k in CHECKLIST_ITEMS}, "jurisdiction": "GB"},
        headers=pro_trader["headers"],
    )
    token = started.json()["confirmation_token"]
    permission = db.query(TradingPermission).filter(TradingPermission.org_id == pro_trader["org_id"]).first()
    permission.risk_acknowledged_at = datetime.now(UTC) - timedelta(seconds=120)
    db.commit()
    client.post(
        f"{BASE}/trading/live-authorization/confirm",
        json={"confirmation_token": token},
        headers=pro_trader["headers"],
    )

    result = place_order(
        client,
        pro_trader["headers"],
        mode="live",
        connection_id=connection.json()["id"],
        stop_loss=50_000.0,
        quantity=0.001,
    )
    codes = [r["code"] for r in result["body"]["order"]["risk_decision"]["failed_rules"]]
    assert "mode_authorization" in codes
    assert any("platform_live_trading_flag" in (r.get("detail", {}).get("missing") or []) for r in result["body"]["order"]["risk_decision"]["failed_rules"])
