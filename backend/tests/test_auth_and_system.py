from __future__ import annotations

import json

from tests.conftest import BASE, PASSWORD, login, unique_email


def test_health_and_public_config(client):
    health = client.get(f"{BASE}/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    config = client.get(f"{BASE}/config")
    assert config.status_code == 200
    body = config.json()
    assert body["live_trading_enabled"] is False
    # Integration readiness is reported as booleans so a deployment can be checked
    # without a session and without exposing a credential.
    assert body["email"]["delivery_configured"] in (True, False)
    assert body["deriv_oauth_configured"] in (True, False)
    assert "resend_api_key" not in str(body)
    assert "client_secret" not in str(body)
    assert "not custody" in body["disclaimer"] or "does not custody" in body["disclaimer"]

    ready = client.get(f"{BASE}/ready")
    assert ready.json()["database"] is True


def test_security_headers_present(client):
    response = client.get(f"{BASE}/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers.get("X-Request-ID")


def test_registration_login_and_me(client, trader):
    me = client.get(f"{BASE}/auth/me", headers=trader["headers"])
    assert me.status_code == 200
    body = me.json()
    assert body["user"]["email"] == trader["email"]
    assert body["user"]["email_verified"] is True
    assert body["entitlements"]["plan_code"] == "free"
    assert body["live"]["live_enabled"] is False
    assert body["platform"]["live_trading_enabled"] is False


def test_unverified_user_cannot_login(client):
    email = unique_email("unverified")
    response = client.post(
        f"{BASE}/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Unverified", "accept_terms": True},
    )
    assert response.status_code == 201
    attempt = client.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD})
    assert attempt.status_code == 403
    assert attempt.json()["detail"]["code"] == "email_unverified"


def test_weak_password_rejected(client):
    response = client.post(
        f"{BASE}/auth/register",
        json={"email": unique_email(), "password": "weak", "full_name": "Weak", "accept_terms": True},
    )
    assert response.status_code in (400, 422)
    assert "password" in json.dumps(response.json()).lower()


def test_duplicate_email_rejected(client, trader):
    response = client.post(
        f"{BASE}/auth/register",
        json={"email": trader["email"], "password": PASSWORD, "full_name": "Dup", "accept_terms": True},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "email_in_use"


def test_login_failure_is_generic_and_audited(client, trader, db):
    response = client.post(f"{BASE}/auth/login", json={"email": trader["email"], "password": "WrongPassword!1"})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_credentials"

    unknown = client.post(f"{BASE}/auth/login", json={"email": "nobody@example.com", "password": "WrongPassword!1"})
    assert unknown.status_code == 401
    assert unknown.json()["detail"]["message"] == response.json()["detail"]["message"]

    from app.db.models import AuditLog

    assert db.query(AuditLog).filter(AuditLog.action == "user.login_failed").count() >= 1


def test_refresh_requires_csrf_and_rotates(client, trader):
    # TestClient keeps the refresh cookie from login.
    no_csrf = client.post(f"{BASE}/auth/refresh")
    assert no_csrf.status_code == 401
    assert no_csrf.json()["detail"]["code"] == "csrf_failed"

    csrf = client.cookies.get("veltrane_csrf")
    rotated = client.post(f"{BASE}/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert rotated.status_code == 200, rotated.text
    new_access = rotated.json()["access_token"]
    assert new_access != trader["access_token"]
    me = client.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200


def test_refresh_token_cannot_be_used_as_access_token(client, trader):
    # A refresh token must not authenticate API calls.
    cookie = client.cookies.get("veltrane_refresh")
    response = client.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {cookie}"})
    assert response.status_code == 401


def test_mfa_enrolment_and_login(client, trader):
    setup = client.post(f"{BASE}/auth/mfa/setup", headers=trader["headers"])
    assert setup.status_code == 200
    secret = setup.json()["secret"]

    import pyotp

    code = pyotp.TOTP(secret).now()
    enabled = client.post(f"{BASE}/auth/mfa/enable", json={"code": code}, headers=trader["headers"])
    assert enabled.status_code == 200
    recovery = enabled.json()["recovery_codes"]
    assert len(recovery) == 8

    # Password alone now returns an MFA challenge, not a session.
    challenge = client.post(f"{BASE}/auth/login", json={"email": trader["email"], "password": PASSWORD})
    assert challenge.status_code == 200
    assert challenge.json()["mfa_required"] is True
    mfa_token = challenge.json()["mfa_token"]

    bad = client.post(f"{BASE}/auth/mfa/verify", json={"mfa_token": mfa_token, "code": "000000"})
    assert bad.status_code == 400

    good = client.post(f"{BASE}/auth/mfa/verify", json={"mfa_token": mfa_token, "code": pyotp.TOTP(secret).now()})
    assert good.status_code == 200
    assert good.json()["access_token"]

    # Recovery code works once and is consumed.
    challenge2 = client.post(f"{BASE}/auth/login", json={"email": trader["email"], "password": PASSWORD})
    used = client.post(
        f"{BASE}/auth/mfa/verify",
        json={"mfa_token": challenge2.json()["mfa_token"], "code": recovery[0]},
    )
    assert used.status_code == 200
    challenge3 = client.post(f"{BASE}/auth/login", json={"email": trader["email"], "password": PASSWORD})
    reused = client.post(
        f"{BASE}/auth/mfa/verify",
        json={"mfa_token": challenge3.json()["mfa_token"], "code": recovery[0]},
    )
    assert reused.status_code == 400


def test_password_reset_flow(client, trader):
    forgot = client.post(f"{BASE}/auth/password/forgot", json={"email": trader["email"]})
    assert forgot.status_code == 200
    token = forgot.json()["debug_reset_token"]
    new_password = "Veltrane!Reset2026"
    reset = client.post(f"{BASE}/auth/password/reset", json={"token": token, "new_password": new_password})
    assert reset.status_code == 200
    login(client, trader["email"], new_password)
    old = client.post(f"{BASE}/auth/login", json={"email": trader["email"], "password": PASSWORD})
    assert old.status_code == 401


def test_logout_revokes_refresh(client, trader):
    response = client.post(f"{BASE}/auth/logout")
    assert response.status_code == 200
    assert client.cookies.get("veltrane_refresh") is None


def test_audit_log_redacts_secrets(client, trader, db):
    from app.db.models import AuditLog

    entry = db.query(AuditLog).filter(AuditLog.action == "user.registered", AuditLog.org_id == trader["org_id"]).first()
    assert entry is not None
    assert "password" not in json.dumps(entry.meta).lower()
