from __future__ import annotations

from tests.conftest import BASE


def create_connection(client, headers, **overrides):
    payload = {
        "provider": "paper",
        "label": f"Sim {overrides.pop('label', 'account')}",
        "environment": "paper",
    }
    payload.update(overrides)
    return client.post(f"{BASE}/connections", json=payload, headers=headers)


def test_provider_catalog_is_honest(client):
    catalog = client.get(f"{BASE}/connections/providers").json()
    providers = {p["key"]: p for p in catalog["providers"]}
    assert "binance" in providers and "bybit" in providers and "okx" in providers
    assert providers["binance"]["status"] == "implemented_unverified"
    assert providers["deriv"]["status"] in ("scaffold", "implemented_unverified")
    assert "not been verified" in catalog["notice"]
    for provider in providers.values():
        assert provider["capabilities"]["place_order"] is False or provider["status"] == "implemented_unverified"
        assert "withdraw" not in provider["capabilities"]


def test_paper_connection_sync_produces_balances(client, trader):
    created = create_connection(client, trader["headers"], label="Simulation")
    assert created.status_code == 201, created.text
    connection = created.json()
    assert connection["provider"] == "paper"
    assert connection["environment"] == "paper"
    assert connection["permissions"]["trade"] is False  # simulated, not a real venue

    synced = client.post(f"{BASE}/connections/{connection['id']}/sync", headers=trader["headers"])
    assert synced.status_code == 200, synced.text
    balances = client.get(f"{BASE}/connections/{connection['id']}/balances", headers=trader["headers"]).json()
    assert balances["balances"]
    assert balances["stale"] is False


def test_crypto_credentials_encrypted_and_never_returned(client, trader, db):
    created = create_connection(
        client,
        trader["headers"],
        provider="binance",
        label="Binance main",
        environment="read_only",
        api_key="PUBLICKEY1234567890",
        api_secret="SUPERSECRETVALUE0987654321",
        withdrawal_attestation=True,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    text = str(body)
    assert "SUPERSECRETVALUE0987654321" not in text
    assert "PUBLICKEY1234567890" not in text
    assert body["credential"]["key_hint"].endswith("7890")

    from app.db.models import ConnectionCredential

    credential = db.query(ConnectionCredential).one()
    assert "SUPERSECRETVALUE" not in credential.envelope
    assert "PUBLICKEY" not in credential.envelope
    assert body["permissions"]["withdrawal_attestation"] is True
    assert body["permissions"]["withdraw"] is False

    listing = client.get(f"{BASE}/connections", headers=trader["headers"])
    assert "SUPERSECRETVALUE0987654321" not in listing.text


def test_unknown_provider_is_rejected(client, trader):
    response = create_connection(
        client,
        trader["headers"],
        provider="not-a-venue",
        label="Nope",
        environment="read_only",
        api_key="abc",
        api_secret="def",
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "provider_not_found"


def test_deriv_asks_for_a_token_and_an_app_id_not_a_secret(client):
    catalog = client.get(f"{BASE}/connections/providers").json()
    deriv = {p["key"]: p for p in catalog["providers"]}["deriv"]

    assert deriv["requires_api_secret"] is False
    assert deriv["requires_app_id"] is True
    assert deriv["token_label"]


def test_missing_credentials_rejected(client, trader):
    response = create_connection(
        client, trader["headers"], provider="binance", label="No keys", environment="read_only"
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "missing_credentials"


def test_duplicate_label_rejected(client, trader):
    first = create_connection(client, trader["headers"], label="Same name")
    assert first.status_code == 201
    second = create_connection(client, trader["headers"], label="Same name")
    assert second.status_code == 409


def test_free_connection_limit_is_enforced_server_side(client, trader):
    for i in range(2):
        assert create_connection(client, trader["headers"], label=f"Sim {i}").status_code == 201
    third = create_connection(client, trader["headers"], label="Sim 3")
    assert third.status_code == 403
    assert third.json()["detail"]["code"] == "connection_limit_reached"

    listing = client.get(f"{BASE}/connections", headers=trader["headers"]).json()
    assert listing["limit"] == 2
    assert listing["used"] == 2


def test_unreachable_venue_fails_at_connect_time(client, trader, stub_hosted_venues):
    stub_hosted_venues.fail_code = "provider_error"
    stub_hosted_venues.fail_message = "venue unreachable"

    created = create_connection(
        client,
        trader["headers"],
        provider="binance",
        label="Unreachable",
        environment="read_only",
        api_key="invalid-key",
        api_secret="invalid-secret",
    )
    # Verification happens before anything is persisted, so the failure is a clean coded error.
    assert created.status_code == 400
    assert created.json()["detail"]["code"] == "provider_error"
    assert "Traceback" not in created.text

    listing = client.get(f"{BASE}/connections", headers=trader["headers"]).json()
    assert listing["connections"] == []


def test_outage_after_connect_marks_the_connection_errored(client, trader, db, stub_hosted_venues):
    created = create_connection(
        client,
        trader["headers"],
        provider="binance",
        label="Flaky venue",
        environment="read_only",
        api_key="key-abcdef",
        api_secret="secret-abcdef",
    )
    assert created.status_code == 201, created.text

    stub_hosted_venues.fail_code = "provider_error"
    result = client.post(f"{BASE}/connections/{created.json()['id']}/test", headers=trader["headers"])

    # The failure is surfaced as a safe, coded error rather than a 500 or a stack trace.
    assert result.status_code == 400
    assert result.json()["detail"]["code"]
    assert "Traceback" not in result.text
    detail = client.get(f"{BASE}/connections/{created.json()['id']}", headers=trader["headers"]).json()
    assert detail["status"] == "error"
    assert detail["last_error"]

    notes = client.get(f"{BASE}/notifications", headers=trader["headers"]).json()["notifications"]
    assert any(n["category"] == "connection" for n in notes)


def test_connection_success_path_reports_connected(client, trader):
    created = create_connection(client, trader["headers"], label="Testable")
    assert created.status_code == 201
    connection_id = created.json()["id"]

    result = client.post(f"{BASE}/connections/{connection_id}/test", headers=trader["headers"])
    assert result.status_code == 200, result.text
    assert result.json()["ok"] is True

    detail = client.get(f"{BASE}/connections/{connection_id}", headers=trader["headers"]).json()
    assert detail["status"] == "connected"
    assert detail["last_error"] is None
    assert detail["permissions"]["trade"] is False


def test_revoke_removes_credentials(client, trader, db):
    created = create_connection(
        client,
        trader["headers"],
        provider="binance",
        label="To revoke",
        environment="read_only",
        api_key="key-123456",
        api_secret="secret-123456",
    )
    connection_id = created.json()["id"]
    revoked = client.delete(f"{BASE}/connections/{connection_id}", headers=trader["headers"])
    assert revoked.status_code == 200

    from app.db.models import ConnectionCredential

    assert db.query(ConnectionCredential).filter(ConnectionCredential.connection_id == connection_id).count() == 0
    after = client.get(f"{BASE}/connections/{connection_id}", headers=trader["headers"]).json()
    assert after["status"] == "revoked"
    assert after["credential"] is None


def test_credential_rotation(client, trader):
    created = create_connection(
        client,
        trader["headers"],
        provider="binance",
        label="Rotate me",
        environment="read_only",
        api_key="old-key-1111",
        api_secret="old-secret",
    )
    connection_id = created.json()["id"]
    rotated = client.post(
        f"{BASE}/connections/{connection_id}/rotate-credentials",
        json={"api_key": "new-key-2222", "api_secret": "new-secret"},
        headers=trader["headers"],
    )
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["credential"]["key_hint"].endswith("2222")
    assert "new-secret" not in rotated.text
