from __future__ import annotations

import pytest

BASE = "/api/v1"


def test_paper_session_is_provisioned_once(client, trader):
    first = client.post(f"{BASE}/trading/paper-session", headers=trader["headers"])
    assert first.status_code == 201, first.text
    session = first.json()
    assert session["status"] == "running"
    assert session["starting_balance"] == 25000.0
    assert session["equity"] == 25000.0

    second = client.post(f"{BASE}/trading/paper-session", headers=trader["headers"])
    assert second.status_code == 201
    assert second.json()["id"] == session["id"], "a second call must not create a second session"


def test_overview_reports_the_paper_session(client, trader):
    created = client.post(f"{BASE}/trading/paper-session", headers=trader["headers"]).json()
    overview = client.get(f"{BASE}/portfolio/overview", headers=trader["headers"]).json()
    assert overview["equity"]["simulated_source"] == "paper_session"
    assert overview["equity"]["simulated_balance_usd"] == 25000.0
    assert overview["paper_session"]["id"] == created["id"]


def test_paper_session_is_tenant_scoped(client, trader, trader2):
    mine = client.post(f"{BASE}/trading/paper-session", headers=trader["headers"]).json()
    theirs = client.post(f"{BASE}/trading/paper-session", headers=trader2["headers"]).json()
    assert mine["id"] != theirs["id"]

@pytest.fixture
def trader(basic_trader):
    """Execution tests need a plan that may execute: Free accounts cannot trade."""
    return basic_trader
