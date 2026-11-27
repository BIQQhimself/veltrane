"""Account identity, profile editing and the wallet view."""

from __future__ import annotations

from datetime import UTC, datetime

from app.db.models import Balance, Connection, LedgerTransaction

BASE = "/api/v1"


def _connection(db, account, **overrides) -> Connection:
    defaults = {
        "org_id": account["org_id"],
        "created_by": account["user_id"],
        "kind": "broker",
        "provider": "deriv",
        "label": f"conn-{account['org_id'][:6]}",
        "environment": "read_only",
        "status": "connected",
    }
    defaults.update(overrides)
    row = Connection(**defaults)
    db.add(row)
    db.commit()
    return row


def test_me_exposes_identity_and_automation_state(client, trader):
    body = client.get(f"{BASE}/auth/me", headers=trader["headers"]).json()
    assert body["identity"]["display_name"] == "Test"
    assert body["identity"]["public_id"].startswith("VT-")
    assert len(body["identity"]["public_id"]) == 11
    assert body["identity"]["avatar_color"].startswith("#")
    assert body["automation"]["mode"] == "none"


def test_profile_update_changes_display_name_only(client, trader, db):
    response = client.patch(
        f"{BASE}/auth/profile",
        json={"display_name": "  Alex   Morgan  ", "avatar_color": "#12b981"},
        headers=trader["headers"],
    )
    assert response.status_code == 200, response.text
    identity = response.json()["identity"]
    assert identity["display_name"] == "Alex Morgan"
    assert identity["avatar_color"] == "#12b981"
    # The legal name on the account is untouched.
    assert identity["full_name"] == "Test Trader"


def test_profile_rejects_bad_values(client, trader):
    empty = client.patch(f"{BASE}/auth/profile", json={"display_name": " "}, headers=trader["headers"])
    assert empty.status_code == 400
    assert empty.json()["detail"]["code"] == "invalid_profile"

    colour = client.patch(f"{BASE}/auth/profile", json={"avatar_color": "red"}, headers=trader["headers"])
    assert colour.status_code == 400

    long_name = client.patch(
        f"{BASE}/auth/profile", json={"display_name": "x" * 80}, headers=trader["headers"]
    )
    assert long_name.status_code in (400, 422)


def test_profile_requires_authentication(client):
    assert client.patch(f"{BASE}/auth/profile", json={"display_name": "Nope"}).status_code == 401


def test_wallet_separates_live_and_simulated_money(client, trader, db):
    live = _connection(db, trader, label="live-account", environment="live", provider_account_type="real")
    demo = _connection(db, trader, label="demo-account", environment="demo", provider_account_type="demo")
    now = datetime.now(UTC)
    db.add_all(
        [
            Balance(
                org_id=trader["org_id"],
                connection_id=live.id,
                asset="USD",
                free=500,
                locked=0,
                total=500,
                usd_value=500,
                as_of=now,
            ),
            Balance(
                org_id=trader["org_id"],
                connection_id=demo.id,
                asset="USD",
                free=10000,
                locked=0,
                total=10000,
                usd_value=10000,
                as_of=now,
            ),
            LedgerTransaction(
                org_id=trader["org_id"],
                connection_id=live.id,
                type="deposit",
                asset="USD",
                amount=500,
                fee=0,
                occurred_at=now,
            ),
        ]
    )
    db.commit()

    body = client.get(f"{BASE}/wallet", headers=trader["headers"]).json()
    assert body["totals"]["live_usd"] == 500
    assert body["totals"]["demo_usd"] == 10000
    assert body["funding"]["veltrane_holds_funds"] is False
    assert {a["label"] for a in body["accounts"]} == {"live-account", "demo-account"}
    assert [t["type"] for t in body["transactions"]] == ["deposit"]
    assert body["transactions"][0]["simulated"] is False


def test_wallet_is_tenant_scoped(client, trader, trader2, db):
    _connection(db, trader2, label="other-tenant")
    body = client.get(f"{BASE}/wallet", headers=trader["headers"]).json()
    assert body["accounts"] == []
    assert body["transactions"] == []


def test_wallet_requires_authentication(client):
    assert client.get(f"{BASE}/wallet").status_code == 401


def test_support_ticket_round_trip(client, trader):
    created = client.post(
        f"{BASE}/support/tickets",
        json={"subject": "Deriv reconnect", "body": "My Deriv session expired after an hour.", "priority": "high"},
        headers=trader["headers"],
    )
    assert created.status_code == 201, created.text
    ticket = created.json()
    assert ticket["status"] == "open"

    reply = client.post(
        f"{BASE}/support/tickets/{ticket['id']}/messages",
        json={"message": "It happened again this morning."},
        headers=trader["headers"],
    )
    assert reply.status_code == 201, reply.text
    assert len(reply.json()["messages"]) == 2
    assert reply.json()["messages"][-1]["role"] == "user"

    listed = client.get(f"{BASE}/support/tickets", headers=trader["headers"]).json()["tickets"]
    assert [t["id"] for t in listed] == [ticket["id"]]


def test_support_tickets_are_tenant_scoped(client, trader, trader2):
    created = client.post(
        f"{BASE}/support/tickets",
        json={"subject": "Question", "body": "How do I rotate my API token safely?"},
        headers=trader["headers"],
    ).json()
    other = client.get(f"{BASE}/support/tickets", headers=trader2["headers"]).json()["tickets"]
    assert other == []
    cross = client.post(
        f"{BASE}/support/tickets/{created['id']}/messages",
        json={"message": "Not my ticket."},
        headers=trader2["headers"],
    )
    assert cross.status_code == 404


def test_support_rejects_a_short_body(client, trader):
    response = client.post(
        f"{BASE}/support/tickets",
        json={"subject": "Hi", "body": "help"},
        headers=trader["headers"],
    )
    assert response.status_code == 422
