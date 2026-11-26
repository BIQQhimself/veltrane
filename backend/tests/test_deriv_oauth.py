"""Deriv OAuth 2.0 + PKCE: handshake, callback, token storage and account switching.

The token endpoint is the local protocol mock (tests/support/deriv_mock.py), so these tests
exercise the real adapter and the real exchange code without touching Deriv.
"""

from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest
from tests.conftest import BASE


@pytest.fixture()
def oauth_env(deriv_env, mock_deriv, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "deriv_oauth_client_id", "app_test_12345")
    monkeypatch.setattr(settings, "deriv_oauth_redirect_uri", "https://api.veltrane.test/api/v1/deriv/oauth/callback")
    monkeypatch.setattr(settings, "deriv_oauth_token_url", f"{mock_deriv.base_url}/oauth2/token")
    monkeypatch.setattr(settings, "deriv_oauth_auth_url", "https://auth.deriv.test/oauth2/auth")
    monkeypatch.setattr(settings, "web_base_url", "https://app.veltrane.test")
    return mock_deriv


def start_oauth(client, trader, **overrides) -> dict:
    payload = {"purpose": "connect", "visitor_id": "visitor-abc12345"}
    payload.update(overrides)
    response = client.post(f"{BASE}/deriv/oauth/start", json=payload, headers=trader["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def complete(client, trader, started: dict, code: str = "mock_code_123") -> dict:
    response = client.post(
        f"{BASE}/deriv/oauth/exchange",
        json={"code": code, "state": started["state"]},
        headers=trader["headers"],
    )
    return {"status": response.status_code, "body": response.json() if response.content else {}}


def test_start_builds_a_pkce_authorisation_url(oauth_env, client, trader):
    body = start_oauth(client, trader)

    url = urlparse(body["authorize_url"])
    assert f"{url.scheme}://{url.netloc}" == "https://auth.deriv.test"
    params = {key: values[0] for key, values in parse_qs(url.query).items()}
    assert params["response_type"] == "code"
    assert params["client_id"] == "app_test_12345"
    assert params["code_challenge_method"] == "S256"
    assert params["redirect_uri"] == "https://api.veltrane.test/api/v1/deriv/oauth/callback"
    assert params["state"] == body["state"]
    assert len(params["code_challenge"]) >= 43
    # Scopes are exactly what execution needs, and never the payment (withdrawal) scope.
    assert set(params["scope"].split()) == {"trade", "account_manage"}
    assert "payment" not in params["scope"]
    # People without a Deriv account are offered the referral link, opened in a new tab.
    assert body["referral_url"].startswith("https://t.deriv.link")
    assert "t=XXSKPY9YLQB2" in body["referral_url"]


def test_oauth_requires_configuration(client, trader):
    response = client.post(f"{BASE}/deriv/oauth/start", json={}, headers=trader["headers"])
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "deriv_oauth_not_configured"


def test_callback_creates_one_encrypted_connection(oauth_env, client, trader, db):
    from app.db.models import Connection, ConnectionCredential

    started = start_oauth(client, trader)
    response = client.get(
        f"{BASE}/deriv/oauth/callback",
        params={"code": "mock_code_123", "state": started["state"]},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "deriv=connected" in response.headers["location"]
    assert response.headers["location"].startswith("https://app.veltrane.test/app/accounts")

    connections = db.query(Connection).filter(Connection.org_id == trader["org_id"]).all()
    deriv = [row for row in connections if row.provider == "deriv"]
    assert len(deriv) == 1
    connection = deriv[0]
    assert connection.status == "connected"
    assert connection.provider_account_id in {"VRTC900001", "CR700001"}
    accounts = connection.provider_meta["accounts"]
    assert {row["account_type"] for row in accounts} == {"demo", "real"}
    assert connection.provider_meta["oauth"]["expires_at"]
    assert connection.provider_meta["one_account_policy"] is True

    credential = db.query(ConnectionCredential).filter_by(connection_id=connection.id).one()
    assert "ory_at_mock_access_token" not in str(credential.envelope)
    # The exchange sent the verifier that matches the challenge it published.
    sent = oauth_env.state.oauth_requests[-1]
    challenge = parse_qs(urlparse(started["authorize_url"]).query)["code_challenge"][0]
    expected = base64.urlsafe_b64encode(hashlib.sha256(sent["code_verifier"].encode()).digest()).decode().rstrip("=")
    assert challenge == expected


def test_state_is_single_use(oauth_env, client, trader):
    started = start_oauth(client, trader)
    first = complete(client, trader, started)
    assert first["status"] == 200, first
    replay = complete(client, trader, started)
    assert replay["status"] == 400
    assert replay["body"]["detail"]["code"] == "oauth_state_used"


def test_state_cannot_be_used_by_another_account(oauth_env, client, trader, trader2):
    started = start_oauth(client, trader)
    response = client.post(
        f"{BASE}/deriv/oauth/exchange",
        json={"code": "mock_code_123", "state": started["state"]},
        headers=trader2["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "oauth_state_owner_mismatch"


def test_rejected_code_is_reported_without_creating_a_connection(oauth_env, client, trader, db):
    from app.db.models import Connection

    started = start_oauth(client, trader)
    response = client.post(
        f"{BASE}/deriv/oauth/exchange",
        json={"code": "not-a-code", "state": started["state"]},
        headers=trader["headers"],
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "deriv_oauth_rejected"
    assert db.query(Connection).filter(Connection.org_id == trader["org_id"], Connection.provider == "deriv").count() == 0


def test_denied_consent_redirects_without_error_page(oauth_env, client):
    response = client.get(f"{BASE}/deriv/oauth/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert response.status_code == 302
    assert "deriv=denied" in response.headers["location"]


def test_reconnect_updates_the_same_connection(oauth_env, client, trader, db):
    from app.db.models import Connection

    first = complete(client, trader, start_oauth(client, trader))
    assert first["status"] == 200
    second = complete(client, trader, start_oauth(client, trader, purpose="reconnect"))
    assert second["status"] == 200
    assert second["body"]["created"] is False
    rows = db.query(Connection).filter(Connection.org_id == trader["org_id"], Connection.provider == "deriv").all()
    assert len(rows) == 1


def test_account_switch_between_demo_and_real(oauth_env, client, trader, db):
    from app.db.models import Connection

    complete(client, trader, start_oauth(client, trader))
    connection = (
        db.query(Connection).filter(Connection.org_id == trader["org_id"], Connection.provider == "deriv").one()
    )
    real = client.post(
        f"{BASE}/deriv/connections/{connection.id}/account",
        json={"account_id": "CR700001"},
        headers=trader["headers"],
    )
    assert real.status_code == 200, real.text
    assert real.json()["account_type"] == "real"
    assert real.json()["is_demo"] is False

    demo = client.post(
        f"{BASE}/deriv/connections/{connection.id}/account",
        json={"account_id": "VRTC900001"},
        headers=trader["headers"],
    )
    assert demo.status_code == 200
    assert demo.json()["is_demo"] is True

    unknown = client.post(
        f"{BASE}/deriv/connections/{connection.id}/account",
        json={"account_id": "ZZZ000000"},
        headers=trader["headers"],
    )
    assert unknown.status_code == 400
    assert unknown.json()["detail"]["code"] == "account_not_available"


def test_status_and_exchange_never_return_the_access_token(oauth_env, client, trader, db):
    from app.db.models import Connection

    complete(client, trader, start_oauth(client, trader))
    status = client.get(f"{BASE}/deriv/oauth/status", headers=trader["headers"])
    assert status.status_code == 200
    body = status.json()
    assert body["configured"] is True
    assert body["single_account_policy"] is True
    assert body["referral"]["url"].startswith("https://t.deriv.link")
    assert body["connection"]["token"]["kind"] == "oauth"
    assert body["connection"]["token"]["expired"] is False
    assert "ory_at_mock_access_token" not in status.text
    assert "client_secret" not in status.text

    connection = (
        db.query(Connection).filter(Connection.org_id == trader["org_id"], Connection.provider == "deriv").one()
    )
    detail = client.get(f"{BASE}/deriv/connections/{connection.id}/status", headers=trader["headers"])
    assert "ory_at_mock_access_token" not in detail.text


def test_expired_token_is_reported_and_reconnect_required(oauth_env, client, trader, db):
    from app.db.models import Connection

    complete(client, trader, start_oauth(client, trader))
    connection = (
        db.query(Connection).filter(Connection.org_id == trader["org_id"], Connection.provider == "deriv").one()
    )
    connection.provider_meta = {
        **connection.provider_meta,
        "oauth": {**connection.provider_meta["oauth"], "expires_at": "2020-01-01T00:00:00+00:00"},
    }
    db.commit()
    body = client.get(f"{BASE}/deriv/oauth/status", headers=trader["headers"]).json()
    assert body["connection"]["token"]["expired"] is True


def test_oauth_start_records_a_referral_funnel_step(oauth_env, client, trader, db):
    from app.db.models import ReferralEvent

    start_oauth(client, trader, visitor_id="visitor-funnel01")
    kinds = {
        row.kind
        for row in db.query(ReferralEvent).filter(ReferralEvent.user_id == trader["user_id"]).all()
    }
    assert "oauth_start" in kinds
    complete(client, trader, start_oauth(client, trader))
    kinds = {
        row.kind
        for row in db.query(ReferralEvent).filter(ReferralEvent.user_id == trader["user_id"]).all()
    }
    assert "connection" in kinds
