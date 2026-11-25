from __future__ import annotations

from tests.conftest import BASE, place_order


def test_orders_trades_positions_are_tenant_isolated(client, trader, trader2):
    buy = place_order(client, trader["headers"], quantity=0.01)
    order_id = buy["body"]["order"]["id"]
    position_id = client.get(f"{BASE}/positions", headers=trader["headers"]).json()["positions"][0]["id"]
    closed = client.post(
        f"{BASE}/positions/{position_id}/close", json={"reason": "test"}, headers=trader["headers"]
    )
    trade_id = closed.json()["trade"]["id"]

    assert client.get(f"{BASE}/orders/{order_id}", headers=trader2["headers"]).status_code == 404
    assert client.get(f"{BASE}/trades/{trade_id}", headers=trader2["headers"]).status_code == 404
    assert client.get(f"{BASE}/positions", headers=trader2["headers"]).json()["positions"] == []
    assert client.get(f"{BASE}/orders", headers=trader2["headers"]).json()["orders"] == []
    assert client.get(f"{BASE}/trades", headers=trader2["headers"]).json()["trades"] == []
    assert (
        client.post(
            f"{BASE}/positions/{position_id}/close", json={"reason": "hijack"}, headers=trader2["headers"]
        ).status_code
        == 404
    )


def test_connections_are_tenant_isolated(client, trader, trader2):
    created = client.post(
        f"{BASE}/connections",
        json={"provider": "paper", "label": "Mine", "environment": "paper"},
        headers=trader["headers"],
    )
    connection_id = created.json()["id"]
    for method, path in (
        ("get", f"/connections/{connection_id}"),
        ("get", f"/connections/{connection_id}/balances"),
        ("get", f"/connections/{connection_id}/transactions"),
    ):
        response = getattr(client, method)(f"{BASE}{path}", headers=trader2["headers"])
        assert response.status_code == 404, path
    assert client.post(f"{BASE}/connections/{connection_id}/sync", headers=trader2["headers"]).status_code == 404
    assert client.delete(f"{BASE}/connections/{connection_id}", headers=trader2["headers"]).status_code == 404

    mine = client.get(f"{BASE}/connections", headers=trader2["headers"]).json()
    assert mine["connections"] == []


def test_backtests_and_sessions_are_tenant_isolated(client, pro_trader, trader2, make_user):
    backtest = client.post(
        f"{BASE}/backtests",
        json={"strategy_code": "trend_following_v1", "symbol": "BTC/USDT", "timeframe": "1h"},
        headers=pro_trader["headers"],
    )
    assert backtest.status_code == 201, backtest.text
    backtest_id = backtest.json()["id"]
    assert client.get(f"{BASE}/backtests/{backtest_id}", headers=trader2["headers"]).status_code == 404

    session = client.post(
        f"{BASE}/paper-sessions",
        json={"strategy_code": "trend_following_v1", "symbol": "BTC/USDT", "timeframe": "1h"},
        headers=pro_trader["headers"],
    )
    assert session.status_code == 201, session.text
    session_id = session.json()["id"]
    assert client.get(f"{BASE}/paper-sessions/{session_id}", headers=trader2["headers"]).status_code == 404
    assert client.post(f"{BASE}/paper-sessions/{session_id}/tick", headers=trader2["headers"]).status_code == 404


def test_notifications_are_tenant_isolated(client, trader, trader2):
    place_order(client, trader["headers"], quantity=0.005)
    trader_notes = client.get(f"{BASE}/notifications", headers=trader["headers"]).json()["notifications"]
    other_notes = client.get(f"{BASE}/notifications", headers=trader2["headers"]).json()["notifications"]
    assert trader_notes
    assert other_notes == []
    first = trader_notes[0]["id"]
    assert client.post(f"{BASE}/notifications/{first}/read", headers=trader2["headers"]).status_code == 404


def test_portfolio_is_tenant_isolated(client, trader, trader2):
    place_order(client, trader["headers"], quantity=0.005)
    mine = client.get(f"{BASE}/portfolio/overview", headers=trader["headers"]).json()
    theirs = client.get(f"{BASE}/portfolio/overview", headers=trader2["headers"]).json()
    assert mine["positions"]
    assert theirs["positions"] == []
    assert theirs["equity"]["realized_pnl_net"] == 0


def test_unauthenticated_requests_are_rejected(client):
    for path in ("/orders", "/positions", "/portfolio/overview", "/strategies", "/notifications", "/admin/overview"):
        assert client.get(f"{BASE}{path}").status_code == 401
