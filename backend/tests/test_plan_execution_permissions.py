"""The subscription matrix for trade execution.

The owner-approved entitlements are:

    Free   0 executions          (connect and observe only)
    Basic  600 combined per day
    Pro    1200 combined per day
    Elite  2400 combined per day
    VIP    no VELTRANE cap

"Combined" is the point: paper, venue demo and live share one counter, so switching
environments never doubles the day's allowance. These tests exercise the behaviour through
the API, not the helper, because a passing helper with an unguarded endpoint proves nothing.
"""

from __future__ import annotations

from app.services import entitlements, usage
from app.services.usage import get_usage
from tests.conftest import BASE, place_order


def _contract(client, headers, **overrides):
    payload = {
        "symbol": "BTC/USDT",
        "direction": "call",
        "stake": 50.0,
        "duration_seconds": 60,
        "reason": "Permission matrix test",
    }
    payload.update(overrides)
    return client.post(f"{BASE}/binary/contracts", json=payload, headers=headers)


def test_registration_assigns_free_with_no_execution_allowance(client, make_user):
    account = make_user("freecheck")
    me = client.get(f"{BASE}/auth/me", headers=account["headers"]).json()

    assert me["subscription"]["plan_code"] == "free"
    assert me["usage"]["daily_execution_cap"] == 0
    assert me["usage"]["executions_today"] == 0
    assert me["entitlements"]["limits"]["max_daily_executions"] == 0


def test_free_cannot_execute_a_paper_order(client, trader):
    result = place_order(client, trader["headers"])
    body = result["body"]

    assert body["order"]["status"] == "rejected"
    codes = [rule["code"] for rule in body["order"]["risk_decision"]["failed_rules"]]
    assert "daily_execution_limit" in codes
    assert body["fill"] is None

    orders = client.get(f"{BASE}/orders", headers=trader["headers"]).json()["orders"]
    # The attempt is recorded for audit, but nothing was executed.
    assert all(order["status"] == "rejected" for order in orders)


def test_free_cannot_open_a_simulated_contract(client, trader):
    response = _contract(client, trader["headers"])
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["contract"]["status"] == "rejected"
    assert "execution" in (body["contract"]["rejection_reason"] or "").lower()
    assert body.get("trade") is None


def test_basic_can_execute_and_reports_the_combined_cap(client, basic_trader):
    me = client.get(f"{BASE}/auth/me", headers=basic_trader["headers"]).json()
    assert me["subscription"]["plan_code"] == "basic"
    assert me["usage"]["daily_execution_cap"] == 600

    result = place_order(client, basic_trader["headers"])
    assert result["body"]["order"]["status"] == "filled"

    after = client.get(f"{BASE}/auth/me", headers=basic_trader["headers"]).json()
    assert after["usage"]["executions_today"] == 1


def test_demo_and_paper_share_one_daily_allowance(client, basic_trader):
    assert place_order(client, basic_trader["headers"])["body"]["order"]["status"] == "filled"
    assert _contract(client, basic_trader["headers"]).status_code == 201

    me = client.get(f"{BASE}/auth/me", headers=basic_trader["headers"]).json()
    # Two executions, one allowance: the paper order and the simulated contract both count.
    assert me["usage"]["executions_today"] == 2
    assert me["usage"]["demo_executions_today"] == 2


def test_allowance_exhaustion_blocks_the_next_execution(client, basic_trader, db):
    usage.increment_usage(db, basic_trader["org_id"], "executions", 600)
    db.commit()

    result = place_order(client, basic_trader["headers"])
    codes = [rule["code"] for rule in result["body"]["order"]["risk_decision"]["failed_rules"]]
    assert "daily_execution_limit" in codes
    assert "600" in result["body"]["order"]["rejection_reason"]


def test_vip_is_uncapped_but_still_rated_by_the_other_rules(client, make_user, db):
    account = make_user("vip")
    checkout = client.post(
        f"{BASE}/billing/checkout", json={"plan_code": "vip"}, headers=account["headers"]
    )
    assert checkout.status_code == 200, checkout.text
    client.post(
        f"{BASE}/billing/mock/complete",
        json={"checkout_token": checkout.json()["checkout_token"]},
        headers=account["headers"],
    )
    from tests.conftest import login

    session = login(client, account["email"])
    org_id = account["org_id"]

    assert entitlements.daily_execution_cap(db, org_id) is None

    usage.increment_usage(db, org_id, "executions", 5000)
    db.commit()

    result = place_order(client, session["headers"])
    checks = {check["code"]: check for check in result["body"]["order"]["risk_decision"]["checks"]}
    assert checks["daily_execution_limit"]["passed"] is True
    assert result["body"]["order"]["status"] == "filled"


def test_switching_environment_does_not_reset_the_counter(client, basic_trader, db):
    for _ in range(3):
        assert place_order(client, basic_trader["headers"])["body"]["order"]["status"] == "filled"
    assert get_usage(db, basic_trader["org_id"], "executions") == 3

    # A simulated venue contract afterwards extends the same counter, not a fresh one.
    assert _contract(client, basic_trader["headers"]).status_code == 201
    db.expire_all()
    assert get_usage(db, basic_trader["org_id"], "executions") == 4
