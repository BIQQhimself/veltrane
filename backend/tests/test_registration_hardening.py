"""Registration: field-level validation detail, safe logging, trimming and failure isolation."""

from __future__ import annotations

import logging

import pytest
from app.core.security import password_policy, password_strength_errors
from app.db.models import User
from tests.conftest import BASE, PASSWORD, unique_email


def _register_payload(**overrides) -> dict:
    payload = {
        "email": unique_email("reg"),
        "password": PASSWORD,
        "full_name": "Regression Trader",
        "country": "GB",
        "accept_terms": True,
        "terms_version": "terms-2026-01",
        "referral_visitor_id": "",
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------- 422 detail
@pytest.mark.parametrize(
    "email",
    ["trader@veltrane", "trader@localhost", "trader@example..com", "trader@127.0.0.1"],
)
def test_email_without_a_real_domain_is_rejected_with_a_field_locator(client, email):
    """The browser's type=email accepts these; the API must name the field it refused."""
    response = client.post(f"{BASE}/auth/register", json=_register_payload(email=email))

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "validation_error"
    locations = [entry["loc"] for entry in detail["details"]["errors"]]
    assert ["body", "email"] in locations
    # The form needs a message it can print next to the input.
    assert all(entry["msg"] for entry in detail["details"]["errors"])


def test_terms_refusal_is_reported_against_the_checkbox(client):
    response = client.post(f"{BASE}/auth/register", json=_register_payload(accept_terms=False))

    assert response.status_code == 422
    errors = response.json()["detail"]["details"]["errors"]
    assert [entry["loc"] for entry in errors] == [["body", "accept_terms"]]
    assert "accept the terms" in errors[0]["msg"]


# --------------------------------------------------------------------------- logging
def test_validation_failure_logs_the_path_and_field_names_only(client, caplog):
    email = "leak.probe@veltrane"  # rejected domain, still must not be logged
    secret = "Sup3r-Secret-Value!"

    with caplog.at_level(logging.INFO, logger="veltrane"):
        response = client.post(
            f"{BASE}/auth/register",
            json=_register_payload(email=email, password=secret, full_name="Log Probe"),
        )

    assert response.status_code == 422
    records = [r for r in caplog.records if r.getMessage() == "validation_error"]
    assert records, "a rejected request must leave a diagnostic line"

    fields = records[0].extra_fields
    assert fields["path"] == "/api/v1/auth/register"
    assert fields["method"] == "POST"
    assert "email" in fields["fields"]

    logged = caplog.text
    assert email not in logged
    assert secret not in logged
    assert "Log Probe" not in logged


# --------------------------------------------------------------------------- trimming
def test_email_and_name_are_trimmed_before_validation_and_storage(client):
    email = unique_email("spaced")
    response = client.post(
        f"{BASE}/auth/register",
        json=_register_payload(email=f"  {email.upper()}  ", full_name="  Trimmed Trader  "),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["email"] == email
    assert body["user"]["full_name"] == "Trimmed Trader"


def test_name_of_only_spaces_is_rejected_after_trimming(client):
    response = client.post(f"{BASE}/auth/register", json=_register_payload(full_name="   "))

    assert response.status_code == 422
    assert ["body", "full_name"] in [e["loc"] for e in response.json()["detail"]["details"]["errors"]]


# --------------------------------------------------------------------------- 500 hardening
def test_losing_a_duplicate_race_returns_409_not_500(client, trader, monkeypatch):
    """The pre-check is not atomic; the unique index is. A lost race must not be a 500."""
    from sqlalchemy.orm import Session

    real_query = Session.query

    class _Miss:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

    def query_without_user_hits(self, *entities, **kwargs):
        # Only the duplicate-address pre-check is blinded; everything else queries normally.
        if entities and entities[0] is User:
            return _Miss()
        return real_query(self, *entities, **kwargs)

    monkeypatch.setattr(Session, "query", query_without_user_hits)

    response = client.post(f"{BASE}/auth/register", json=_register_payload(email=trader["email"]))

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "email_in_use"


def test_registration_survives_a_failing_verification_email(client, monkeypatch):
    """A mail outage must never cost the account, and must not poison the transaction."""
    from app.services import auth as auth_service

    def boom(*args, **kwargs):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(auth_service.email_service, "queue_rendered", boom)
    email = unique_email("mailfail")

    response = client.post(f"{BASE}/auth/register", json=_register_payload(email=email))

    assert response.status_code == 201, response.text
    assert response.json()["user"]["email"] == email


def test_registration_survives_a_poisoned_email_statement(client, monkeypatch, db):
    """A statement error inside the mail savepoint must not abort the outer transaction."""
    from app.services import auth as auth_service
    from sqlalchemy.exc import DataError

    def poisoned(*args, **kwargs):
        raise DataError("INSERT INTO email_outbox", {}, Exception("value too long"))

    monkeypatch.setattr(auth_service.email_service, "queue_rendered", poisoned)
    email = unique_email("poison")

    response = client.post(f"{BASE}/auth/register", json=_register_payload(email=email))

    assert response.status_code == 201, response.text
    assert db.query(User).filter(User.email == email).count() == 1


def test_registration_works_without_redis(client, monkeypatch):
    """Redis only sharpens rate limiting; registration must not depend on it."""
    import app.core.rate_limit as rate_limit

    monkeypatch.setattr(rate_limit, "get_redis", lambda: None)
    rate_limit._memory.clear()

    response = client.post(f"{BASE}/auth/register", json=_register_payload())

    assert response.status_code == 201, response.text


# --------------------------------------------------------------------------- password policy
def test_public_config_publishes_the_enforced_password_policy(client):
    body = client.get(f"{BASE}/config").json()

    assert body["password_policy"] == password_policy()
    assert body["password_policy"]["min_length"] == 12
    assert set(body["password_policy"]["requires"]) == {"lowercase", "uppercase", "number", "symbol"}


def test_password_policy_requires_every_documented_rule():
    """The published rules and the enforcement must agree."""
    policy = password_policy()

    for rule in policy["requires"]:
        assert password_strength_errors("Veltrane!2026") == []
        weak = {
            "lowercase": "VELTRANE!2026",
            "uppercase": "veltrane!2026",
            "number": "Veltrane!Test",
            "symbol": "VeltraneTest2026",
        }[rule]
        assert password_strength_errors(weak), f"{rule} should be enforced"
    assert password_strength_errors("Short!1") == ["at least 12 characters"]


def test_weak_password_message_lists_the_rules(client):
    response = client.post(f"{BASE}/auth/register", json=_register_payload(password="alllowercase1!"))

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "weak_password"
    assert "uppercase" in detail["message"]
