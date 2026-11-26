from __future__ import annotations

from tests.conftest import BASE, place_order
from tests.test_billing import checkout_event, send_event

ADMIN_PATHS = [
    "/admin/overview",
    "/admin/revenue",
    "/admin/users",
    "/admin/subscriptions",
    "/admin/payments",
    "/admin/plans",
    "/admin/connections",
    "/admin/trading/activity",
    "/admin/risk/policy",
    "/admin/kill-switches",
    "/admin/feature-flags",
    "/admin/audit",
    "/admin/system/health",
    "/admin/usage",
    "/admin/costs",
    "/admin/performance-fees",
    "/admin/support/tickets",
    "/admin/fraud/signals",
]


def test_member_cannot_reach_admin_surface(client, trader):
    for path in ADMIN_PATHS:
        response = client.get(f"{BASE}{path}", headers=trader["headers"])
        assert response.status_code == 404, (path, response.status_code)
        assert "detail" in response.json()


def test_analyst_cannot_mutate(client, make_user, db):
    from app.db.models import User

    account = make_user("analyst")
    user = db.get(User, account["user_id"])
    user.is_staff = True
    user.staff_role = "analyst"
    db.commit()

    assert client.get(f"{BASE}/admin/overview", headers=account["headers"]).status_code == 200
    mutation = client.put(
        f"{BASE}/admin/risk/policy",
        json={"rules": {"max_position_notional_pct": 50}, "reason": "try"},
        headers=account["headers"],
    )
    assert mutation.status_code == 404


def test_admin_overview_reports_real_metrics(client, trader, admin):
    send_event(client, checkout_event(trader["org_id"], "pro"))
    overview = client.get(f"{BASE}/admin/overview", headers=admin["headers"])
    assert overview.status_code == 200
    body = overview.json()
    assert body["mrr"] >= 49.0
    assert body["arr"] >= body["mrr"] * 11
    assert body["subscribers_by_tier"]["pro"] >= 1
    assert "churn_rate_pct" in body
    assert "contribution_margin" in body
    assert "free_to_paid_conversion_pct" in body
    assert "performance_fee_revenue" in body
    assert body["cost_model"]["infra_monthly_usd"] >= 0

    revenue = client.get(f"{BASE}/admin/revenue", headers=admin["headers"]).json()
    assert revenue["series"]
    assert revenue["breakdown"]


def test_admin_user_management_and_audit(client, trader, admin, db):
    listed = client.get(f"{BASE}/admin/users", headers=admin["headers"], params={"query": trader["email"]}).json()
    assert listed["count"] == 1
    assert listed["users"][0]["plan_code"] == "free"

    suspend = client.patch(
        f"{BASE}/admin/users/{trader['user_id']}",
        json={"status": "suspended", "reason": "fraud review"},
        headers=admin["headers"],
    )
    assert suspend.status_code == 200

    # A suspended user's existing token stops working immediately.
    blocked = client.get(f"{BASE}/auth/me", headers=trader["headers"])
    assert blocked.status_code == 401

    logs = client.get(f"{BASE}/admin/audit", headers=admin["headers"]).json()["entries"]
    assert any(entry["action"] == "admin.action" and entry["target_id"] == trader["user_id"] for entry in logs)


def test_only_owner_can_grant_owner_role(client, trader, admin):
    response = client.patch(
        f"{BASE}/admin/users/{trader['user_id']}",
        json={"is_staff": True, "staff_role": "owner", "reason": "escalation"},
        headers=admin["headers"],
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "role_not_allowed"


def test_global_kill_switch_blocks_every_tenant(client, trader, trader2, admin):
    engaged = client.post(
        f"{BASE}/admin/kill-switches/engage",
        json={"rules": {}, "reason": "Exchange incident"},
        headers=admin["headers"],
    )
    assert engaged.status_code == 200

    for account in (trader, trader2):
        result = place_order(client, account["headers"], quantity=0.001)
        assert result["body"]["order"]["status"] == "rejected"
        assert any(r["code"] == "kill_switch" for r in result["body"]["order"]["risk_decision"]["failed_rules"])

    state = client.get(f"{BASE}/admin/kill-switches", headers=admin["headers"]).json()
    assert state["global_state"]["global"] is True

    released = client.post(
        f"{BASE}/admin/kill-switches/release",
        json={"rules": {}, "reason": "resolved"},
        headers=admin["headers"],
    )
    assert released.status_code == 200
    ok = place_order(client, trader["headers"], quantity=0.001)
    assert ok["body"]["order"]["status"] == "filled"


def test_risk_policy_versioning(client, admin):
    current = client.get(f"{BASE}/admin/risk/policy", headers=admin["headers"]).json()["policy"]
    assert current["version"] == 1

    updated = client.put(
        f"{BASE}/admin/risk/policy",
        json={"rules": {"daily_loss_limit_pct": 2.0}, "reason": "tighten daily loss"},
        headers=admin["headers"],
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["rules"]["daily_loss_limit_pct"] == 2.0

    invalid = client.put(
        f"{BASE}/admin/risk/policy",
        json={"rules": {"not_a_rule": 1}, "reason": "typo"},
        headers=admin["headers"],
    )
    assert invalid.status_code == 400


def test_admin_cannot_see_credentials(client, trader, admin):
    client.post(
        f"{BASE}/connections",
        json={
            "provider": "binance",
            "label": "Secret holder",
            "environment": "read_only",
            "api_key": "ADMINSHOULDNOTSEEKEY",
            "api_secret": "ADMINSHOULDNOTSEESECRET",
        },
        headers=trader["headers"],
    )
    listing = client.get(f"{BASE}/admin/connections", headers=admin["headers"])
    assert listing.status_code == 200
    assert "ADMINSHOULDNOTSEE" not in listing.text
    assert "key_hint" not in listing.json()["connections"][0]
    assert "credential material is never exposed" in listing.json()["note"].lower()


def test_feature_flags_are_admin_only(client, trader, admin):
    update = client.put(
        f"{BASE}/admin/feature-flags/live_trading_ui",
        json={"enabled": True, "description": "enable live UI"},
        headers=admin["headers"],
    )
    assert update.status_code == 200
    flags = client.get(f"{BASE}/admin/feature-flags", headers=admin["headers"]).json()["flags"]
    assert any(f["key"] == "live_trading_ui" and f["enabled"] for f in flags)
    assert client.put(f"{BASE}/admin/feature-flags/x", json={"enabled": True}, headers=trader["headers"]).status_code == 404


def test_support_ticket_workflow(client, trader, admin):
    created = client.post(
        f"{BASE}/support/tickets",
        json={"subject": "Cannot sync", "body": "My Binance sync fails with an error.", "priority": "high"},
        headers=trader["headers"],
    )
    assert created.status_code == 201
    ticket_id = created.json()["id"]

    tickets = client.get(f"{BASE}/admin/support/tickets", headers=admin["headers"]).json()["tickets"]
    assert tickets[0]["id"] == ticket_id

    reply = client.post(
        f"{BASE}/admin/support/tickets/{ticket_id}/reply",
        json={"message": "Please rotate the key and retry.", "status": "pending"},
        headers=admin["headers"],
    )
    assert reply.status_code == 200
    mine = client.get(f"{BASE}/support/tickets", headers=trader["headers"]).json()["tickets"][0]
    assert mine["status"] == "pending"
    assert len(mine["messages"]) == 2


def test_promote_strategy_to_live_is_operator_only(client, pro_trader, admin, db):
    from app.db.models import Strategy, StrategyVersion

    version = db.query(StrategyVersion).join(Strategy).filter(Strategy.code == "trend_following_v1").first()
    denied = client.post(
        f"{BASE}/admin/strategies/{version.id}/promote-live",
        json={"rules": {}, "reason": "x"},
        headers=pro_trader["headers"],
    )
    assert denied.status_code == 404

    promoted = client.post(
        f"{BASE}/admin/strategies/{version.id}/promote-live",
        json={"rules": {}, "reason": "verified in paper for 30 days"},
        headers=admin["headers"],
    )
    assert promoted.status_code == 200
    assert promoted.json()["status"] == "live"


def test_system_health_and_fraud_signals(client, admin):
    health = client.get(f"{BASE}/admin/system/health", headers=admin["headers"]).json()
    assert health["database"]["ok"] is True
    assert health["live_trading_enabled"] is False
    assert any(p["key"] == "binance" for p in health["providers"])

    signals = client.get(f"{BASE}/admin/fraud/signals", headers=admin["headers"]).json()
    assert "failed_login_ips" in signals
    assert "webhook_signature_rejections" in signals


def test_cost_model_round_trip(client, admin):
    updated = client.put(
        f"{BASE}/admin/costs",
        json={"infra_monthly_usd": 120.0, "ai_monthly_usd": 0.0, "support_cost_per_ticket_usd": 6.0, "notes": "single VM"},
        headers=admin["headers"],
    )
    assert updated.status_code == 200
    costs = client.get(f"{BASE}/admin/costs", headers=admin["headers"]).json()["cost_model"]
    assert costs["infra_monthly_usd"] == 120.0

    overview = client.get(f"{BASE}/admin/overview", headers=admin["headers"]).json()
    assert overview["cost_model"]["infra_monthly_usd"] == 120.0
