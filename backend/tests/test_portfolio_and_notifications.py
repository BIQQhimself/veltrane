from __future__ import annotations

from tests.conftest import BASE, place_order


def test_portfolio_overview_separates_simulated_from_live(client, trader):
    connection = client.post(
        f"{BASE}/connections",
        json={"provider": "paper", "label": "Simulation", "environment": "paper"},
        headers=trader["headers"],
    )
    connection_id = connection.json()["id"]
    client.post(f"{BASE}/connections/{connection_id}/sync", headers=trader["headers"])

    overview = client.get(f"{BASE}/portfolio/overview", headers=trader["headers"]).json()
    # With no paper session the simulated figure mirrors the venue balance.
    assert overview["equity"]["simulated_balance_usd"] == 25000.0
    assert overview["equity"]["simulated_source"] == "venue_balances"

    place_order(client, trader["headers"], quantity=0.005)
    overview = client.get(f"{BASE}/portfolio/overview", headers=trader["headers"]).json()
    equity = overview["equity"]
    # A running paper session supersedes the venue mirror: the same virtual capital
    # must never be counted twice.
    assert equity["simulated_source"] == "paper_session"
    assert equity["simulated_balance_usd"] == equity["paper_equity_usd"]
    assert equity["total_usd"] == round(equity["live_balance_usd"] + equity["simulated_balance_usd"], 2)
    assert equity["total_usd"] < 50000.0
    assert equity["live_balance_usd"] == 0.0
    assert overview["has_live_data"] is False
    assert overview["positions"]
    assert overview["allocation"]
    assert "never custodies" in overview["note"] or "No funds are held" in overview["note"]


def test_portfolio_performance_and_analytics_after_round_trip(client, trader):
    place_order(client, trader["headers"], quantity=0.01)
    position = client.get(f"{BASE}/positions", headers=trader["headers"]).json()["positions"][0]
    client.post(f"{BASE}/positions/{position['id']}/close", json={"reason": "take profit"}, headers=trader["headers"])

    performance = client.get(f"{BASE}/portfolio/performance", headers=trader["headers"]).json()
    assert performance["stats"]["trades"] == 1
    assert performance["stats"]["fees"] > 0
    assert performance["curve"]
    assert performance["stats"]["net_pnl"] == performance["curve"][-1]["cumulative"]

    analytics = client.get(f"{BASE}/analytics", headers=trader["headers"]).json()
    assert analytics["symbols"][0]["symbol"] == "BTC/USDT"
    assert analytics["symbols"][0]["trades"] == 1
    assert analytics["costs"]["total"] > 0
    assert analytics["advanced_unlocked"] is False
    assert analytics["net_pnl_total"] == performance["stats"]["net_pnl"]


def test_advanced_analytics_flag_follows_plan(client, pro_trader):
    analytics = client.get(f"{BASE}/analytics", headers=pro_trader["headers"]).json()
    assert analytics["advanced_unlocked"] is True


def test_notifications_for_entry_and_exit(client, trader):
    place_order(client, trader["headers"], quantity=0.005)
    notes = client.get(f"{BASE}/notifications", headers=trader["headers"]).json()
    titles = [n["title"] for n in notes["notifications"]]
    assert any("Simulated fill" in t for t in titles), titles
    assert notes["unread_count"] >= 1

    position = client.get(f"{BASE}/positions", headers=trader["headers"]).json()["positions"][0]
    client.post(f"{BASE}/positions/{position['id']}/close", json={"reason": "test"}, headers=trader["headers"])
    notes = client.get(f"{BASE}/notifications", headers=trader["headers"]).json()
    assert any("Simulated trade closed" in n["title"] for n in notes["notifications"])

    first = notes["notifications"][0]["id"]
    assert client.post(f"{BASE}/notifications/{first}/read", headers=trader["headers"]).status_code == 200
    read_all = client.post(f"{BASE}/notifications/read-all", headers=trader["headers"])
    assert read_all.status_code == 200
    assert client.get(f"{BASE}/notifications", headers=trader["headers"]).json()["unread_count"] == 0


def test_notification_never_claims_execution_on_rejection(client, trader):
    rejected = place_order(client, trader["headers"], quantity=100)
    assert rejected["body"]["order"]["status"] == "rejected"
    titles = [n["title"] for n in client.get(f"{BASE}/notifications", headers=trader["headers"]).json()["notifications"]]
    assert not any("fill" in t.lower() and "rejected" not in t.lower() for t in titles)
    assert any("rejected" in t.lower() for t in titles)


def test_email_outbox_holds_verification_mail_and_marks_nothing_sent(client, trader, db):
    from app.db.models import EmailOutbox

    rows = db.query(EmailOutbox).all()
    assert rows
    assert all(row.status == "queued" for row in rows)
    assert any("verify" in row.subject.lower() for row in rows)

    # Email delivery is an operator maintenance task and is never exposed to subscribers.
    assert client.post(f"{BASE}/admin/maintenance/deliver-emails", headers=trader["headers"]).status_code == 404


def test_market_data_is_labelled(client):
    ticker = client.get(f"{BASE}/markets/ticker/BTC/USDT").json()
    assert ticker["is_demo"] is True
    assert ticker["source"].startswith("demo")
    assert ticker["price"] > 0

    candles = client.get(f"{BASE}/markets/candles/BTC/USDT", params={"timeframe": "1h", "limit": 120}).json()
    assert len(candles["candles"]) == 120
    assert candles["meta"]["is_demo"] is True

    unknown = client.get(f"{BASE}/markets/ticker/NOPE/USDT")
    assert unknown.status_code == 404


def test_onboarding_progress_is_monotonic_and_tenant_scoped(client, trader):
    first = client.post(f"{BASE}/users/me/onboarding", json={"step": 4, "data": {"plan_seen": True}}, headers=trader["headers"])
    assert first.status_code == 200
    assert first.json()["onboarding_step"] == 4

    back = client.post(f"{BASE}/users/me/onboarding", json={"step": 2}, headers=trader["headers"])
    assert back.json()["onboarding_step"] == 4

    forward = client.post(f"{BASE}/users/me/onboarding", json={"step": 9, "data": {"risk_policy_read": True}}, headers=trader["headers"])
    body = forward.json()
    assert body["onboarding_step"] == 9
    assert body["onboarding"]["plan_seen"] is True
    assert body["onboarding"]["risk_policy_read"] is True

    me = client.get(f"{BASE}/auth/me", headers=trader["headers"]).json()
    assert me["user"]["onboarding_step"] == 9

    invalid = client.post(f"{BASE}/users/me/onboarding", json={"step": 42}, headers=trader["headers"])
    assert invalid.status_code == 422

    anonymous = client.post(f"{BASE}/users/me/onboarding", json={"step": 3})
    assert anonymous.status_code == 401
