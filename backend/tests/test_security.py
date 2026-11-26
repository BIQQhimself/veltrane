from __future__ import annotations

import base64

from tests.conftest import BASE, PASSWORD


def test_security_headers_present(client):
    response = client.get(f"{BASE}/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["X-Request-ID"]
    assert response.headers["Cache-Control"] == "no-store"


def test_passwords_are_argon2_hashed(client, trader, db):
    from app.db.models import User

    user = db.get(User, trader["user_id"])
    assert user.password_hash.startswith("$argon2")
    assert PASSWORD not in user.password_hash

    me = client.get(f"{BASE}/auth/me", headers=trader["headers"])
    assert "password" not in me.text.lower()


def test_login_rate_limit(client, trader):
    for _ in range(10):
        attempt = client.post(f"{BASE}/auth/login", json={"email": trader["email"], "password": "wrong-password"})
        assert attempt.status_code in (401, 403, 429)
    blocked = client.post(f"{BASE}/auth/login", json={"email": trader["email"], "password": "wrong-password"})
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "rate_limited"


def test_failed_logins_are_audited(client, trader, db):
    from app.db.models import AuditLog

    client.post(f"{BASE}/auth/login", json={"email": trader["email"], "password": "nope"})
    rows = db.query(AuditLog).filter(AuditLog.action == "user.login_failed").all()
    assert rows
    assert rows[-1].org_id == trader["org_id"]


def test_tampered_token_rejected(client, trader):
    token = trader["access_token"]
    tampered = token[:-3] + ("abc" if not token.endswith("abc") else "def")
    response = client.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {tampered}"})
    assert response.status_code == 401

    forged = base64.urlsafe_b64encode(b'{"sub":"someone","org_id":"x","role":"owner"}').decode().rstrip("=")
    response = client.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {forged}.{forged}.{forged}"})
    assert response.status_code == 401


def test_refresh_requires_csrf_token(client, trader):
    # Login already stored the refresh cookie and returned the CSRF token.
    without = client.post(f"{BASE}/auth/refresh")
    assert without.status_code == 401
    assert without.json()["detail"]["code"] == "csrf_failed"

    with_token = client.post(f"{BASE}/auth/refresh", headers={"X-CSRF-Token": trader["csrf_token"]})
    assert with_token.status_code == 200
    assert with_token.json()["access_token"]


def test_mfa_secret_encrypted_at_rest(client, trader, db):
    from app.db.models import User

    setup = client.post(f"{BASE}/auth/mfa/setup", headers=trader["headers"])
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    assert len(secret) >= 16

    user = db.get(User, trader["user_id"])
    stored = str(user.mfa_secret_enc)
    assert secret not in stored
    assert stored


def test_weak_password_and_bad_email_rejected(client):
    weak = client.post(
        f"{BASE}/auth/register",
        json={"email": "weak@example.com", "password": "password", "full_name": "Weak", "country": "GB", "accept_terms": True},
    )
    assert weak.status_code == 422

    bad_email = client.post(
        f"{BASE}/auth/register",
        json={"email": "not-an-email", "password": PASSWORD, "full_name": "Bad", "country": "GB", "accept_terms": True},
    )
    assert bad_email.status_code == 422

    no_terms = client.post(
        f"{BASE}/auth/register",
        json={"email": "terms@example.com", "password": PASSWORD, "full_name": "Terms", "country": "GB", "accept_terms": False},
    )
    assert no_terms.status_code == 422


def test_unverified_user_cannot_trade(client, make_user):
    account = make_user("unverified", verified=False)
    attempt = client.post(f"{BASE}/auth/login", json={"email": account["email"], "password": PASSWORD})
    assert attempt.status_code in (401, 403)


def test_error_responses_do_not_leak_internals(client, trader):
    missing = client.get(f"{BASE}/orders/does-not-exist", headers=trader["headers"])
    assert missing.status_code == 404
    assert {"code", "message", "details"}.issubset(set(missing.json()["detail"]))
    assert "Traceback" not in missing.text
    assert "psycopg" not in missing.text

    unknown = client.get(f"{BASE}/nope", headers=trader["headers"])
    assert unknown.status_code == 404


def test_no_secret_material_in_openapi(client):
    schema = client.get("/openapi.json").text
    assert "master_encryption_key" not in schema
    assert "test-secret-key" not in schema


def test_logout_revokes_session(client, trader):
    logout = client.post(f"{BASE}/auth/logout", headers=trader["headers"])
    assert logout.status_code == 200
    assert client.get(f"{BASE}/auth/me", headers=trader["headers"]).status_code == 401


def test_dependency_vulnerability_snapshot_documented():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    assert (root / "SECURITY.md").exists()
    assert (root / "THREAT_MODEL.md").exists()


def test_cookie_samesite_rejects_unknown_values(monkeypatch):
    from app.core.config import Settings

    base = dict(
        database_url="postgresql+psycopg://user:pass@localhost:5432/veltrane",
        redis_url="redis://localhost:6379/0",
    )
    monkeypatch.setenv("VELTRANE_COOKIE_SAMESITE", "sometimes")
    try:
        Settings(**base)
    except Exception as exc:  # pydantic ValidationError
        assert "cookie_samesite" in str(exc)
    else:
        raise AssertionError("invalid SameSite value must be rejected")


def test_samesite_none_requires_secure_cookies():
    from app.core.config import Settings

    try:
        Settings(
            database_url="postgresql+psycopg://user:pass@localhost:5432/veltrane",
            cookie_samesite="none",
            cookie_secure=False,
        )
    except RuntimeError as exc:
        assert "COOKIE_SECURE" in str(exc)
    else:
        raise AssertionError("SameSite=None without Secure must be rejected")

    Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/veltrane",
        cookie_samesite="none",
        cookie_secure=True,
    )
