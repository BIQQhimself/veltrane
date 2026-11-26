"""Email operations: preferences, delivery, retries, Resend webhooks, digests and campaigns.

``httpx.post`` is replaced per test, so no message can leave the process. The point of these
tests is the contract the product depends on: nothing is marked sent unless the provider
accepted it, and nothing is delivered to someone who opted out.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from tests.conftest import BASE


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or json.dumps(self._payload)

    def json(self) -> dict:
        return self._payload


@pytest.fixture()
def resend(monkeypatch):
    """Switch the deployment into Resend mode with a programmable transport."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key_123")
    monkeypatch.setattr(settings, "resend_webhook_secret", "whsec_" + base64.b64encode(b"webhook-secret-key").decode())
    calls: list[dict] = []
    state = {"status": 200, "payload": {"id": "re_msg_0001"}}

    def fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002 - mirrors httpx signature
        calls.append({"url": url, "payload": json, "headers": headers})
        return FakeResponse(state["status"], state["payload"], "" if state["status"] < 400 else "provider said no")

    monkeypatch.setattr("app.services.email.httpx.post", fake_post)
    return {"calls": calls, "state": state}


def queue(client, db, trader, subject="Account notice", category="security") -> str:
    from app.db.models import EmailOutbox

    message = EmailOutbox(
        to_email=trader["email"],
        subject=subject,
        body="Body text",
        html="<p>Body text</p>",
        category=category,
        status="queued",
        provider="resend",
        reply_to="support@example.com",
    )
    db.add(message)
    db.commit()
    return message.id


def test_preferences_round_trip_is_audited(client, trader, db):
    from app.db.models import AuditLog, NotificationPreference

    initial = client.get(f"{BASE}/email/preferences", headers=trader["headers"])
    assert initial.status_code == 200
    assert initial.json()["preferences"]["email_enabled"] is True

    updated = client.put(
        f"{BASE}/email/preferences",
        json={"email_enabled": True, "digest_enabled": False, "promotional": False, "categories": {"trade": False}},
        headers=trader["headers"],
    )
    assert updated.status_code == 200, updated.text
    prefs = updated.json()["preferences"]
    assert prefs["digest_enabled"] is False
    assert prefs["promotional"] is False
    assert prefs["categories"]["trade"] is False

    stored = db.query(NotificationPreference).filter_by(user_id=trader["user_id"]).one()
    assert stored.digest_enabled is False
    assert db.query(AuditLog).filter(AuditLog.action == "email.preferences_updated").count() == 1


def test_unsubscribe_token_disables_promotional_mail_only(client, trader, db):
    from app.db.models import NotificationPreference

    client.get(f"{BASE}/email/preferences", headers=trader["headers"])
    pref = db.query(NotificationPreference).filter_by(user_id=trader["user_id"]).one()
    assert pref.promotional is True

    unknown = client.post(f"{BASE}/email/unsubscribe", json={"token": "not-a-real-token-1234"})
    assert unknown.status_code == 200
    assert unknown.json()["status"] == "accepted"

    done = client.post(f"{BASE}/email/unsubscribe", json={"token": pref.unsubscribe_token})
    assert done.status_code == 200
    assert done.json()["status"] == "unsubscribed"
    db.refresh(pref)
    assert pref.promotional is False
    assert pref.email_enabled is True

    preview = client.get(f"{BASE}/email/unsubscribe", params={"token": pref.unsubscribe_token})
    assert preview.json() == {"valid": True, "promotional": False}


def test_outbox_mode_never_claims_delivery(client, trader, db):
    from app.db.models import EmailOutbox
    from app.services import email as email_service

    message_id = queue(client, db, trader)
    summary = email_service.deliver_queued(db, limit=10)
    assert summary["provider"] == "outbox"
    assert summary["sent"] == 0
    row = db.get(EmailOutbox, message_id)
    assert row.status == "queued"
    assert row.provider_status == "outbox_only"
    assert row.sent_at is None


def test_successful_delivery_records_the_provider_id(client, trader, db, resend):
    from app.db.models import EmailOutbox
    from app.services import email as email_service

    message_id = queue(client, db, trader)
    summary = email_service.deliver_queued(db, limit=10)
    assert summary["sent"] == 1
    row = db.get(EmailOutbox, message_id)
    assert row.status == "sent"
    assert row.provider_message_id == "re_msg_0001"
    assert row.sent_at is not None
    assert resend["calls"][0]["headers"]["Idempotency-Key"] == message_id
    assert resend["calls"][0]["payload"]["to"] == [trader["email"]]


def test_rate_limited_delivery_is_retried_with_backoff(client, trader, db, resend):
    from app.db.models import EmailOutbox
    from app.services import email as email_service

    resend["state"].update(status=429, payload={"message": "slow down"})
    message_id = queue(client, db, trader)
    email_service.deliver_queued(db, limit=10)
    row = db.get(EmailOutbox, message_id)
    assert row.status == "queued"
    assert row.attempts == 1
    assert row.next_attempt_at is not None
    assert "429" in (row.error or "")


def test_permanent_failure_stops_retrying(client, trader, db, resend):
    from app.db.models import EmailOutbox
    from app.services import email as email_service

    resend["state"].update(status=422, payload={"message": "invalid from address"})
    message_id = queue(client, db, trader)
    email_service.deliver_queued(db, limit=10)
    row = db.get(EmailOutbox, message_id)
    assert row.status == "failed"
    assert row.next_attempt_at is None


def test_bounced_address_is_suppressed(client, trader, db, resend):
    from app.db.models import EmailOutbox
    from app.services import email as email_service

    first = queue(client, db, trader, subject="First")
    email_service.deliver_queued(db, limit=10)
    bounced = db.get(EmailOutbox, first)
    bounced.status = "bounced"
    db.commit()

    second = queue(client, db, trader, subject="Second")
    email_service.deliver_queued(db, limit=10)
    row = db.get(EmailOutbox, second)
    assert row.status == "suppressed"
    assert len(resend["calls"]) == 1


def sign(secret: str, body: bytes, *, msg_id: str = "msg_1", timestamp: int | None = None) -> dict[str, str]:
    timestamp = timestamp or int(time.time())
    key = base64.b64decode(secret[len("whsec_") :])
    signed = f"{msg_id}.{timestamp}.".encode() + body
    signature = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return {
        "svix-id": msg_id,
        "svix-timestamp": str(timestamp),
        "svix-signature": f"v1,{signature}",
        "content-type": "application/json",
    }


def test_resend_webhook_requires_a_valid_signature(client, trader, db, resend):
    from app.core.config import settings
    from app.db.models import EmailOutbox
    from app.services import email as email_service

    message_id = queue(client, db, trader)
    email_service.deliver_queued(db, limit=10)
    db.get(EmailOutbox, message_id).status = "sent"
    db.commit()

    body = json.dumps({"type": "email.delivered", "data": {"email_id": "re_msg_0001"}}).encode()
    unsigned = client.post(f"{BASE}/webhooks/resend", content=body, headers={"content-type": "application/json"})
    assert unsigned.status_code == 401
    assert unsigned.json()["detail"]["code"] == "invalid_signature"

    tampered = client.post(
        f"{BASE}/webhooks/resend",
        content=body.replace(b"delivered", b"bounced"),
        headers=sign(settings.resend_webhook_secret, body),
    )
    assert tampered.status_code == 401

    stale = client.post(
        f"{BASE}/webhooks/resend",
        content=body,
        headers=sign(settings.resend_webhook_secret, body, timestamp=int(time.time()) - 4000),
    )
    assert stale.status_code == 401

    ok = client.post(f"{BASE}/webhooks/resend", content=body, headers=sign(settings.resend_webhook_secret, body))
    assert ok.status_code == 200, ok.text
    assert ok.json()["matched"] is True
    row = db.get(EmailOutbox, message_id)
    assert row.delivered_at is not None
    assert row.events[-1]["type"] == "email.delivered"


def test_webhook_rejects_when_no_secret_is_configured(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "resend_webhook_secret", "")
    response = client.post(f"{BASE}/webhooks/resend", json={"type": "email.delivered"})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "webhook_not_configured"


def test_bounce_webhook_marks_the_message(client, trader, db, resend):
    from app.core.config import settings
    from app.db.models import EmailOutbox
    from app.services import email as email_service

    message_id = queue(client, db, trader)
    email_service.deliver_queued(db, limit=10)
    body = json.dumps(
        {"type": "email.bounced", "data": {"email_id": "re_msg_0001", "bounce": {"message": "mailbox full"}}}
    ).encode()
    response = client.post(f"{BASE}/webhooks/resend", content=body, headers=sign(settings.resend_webhook_secret, body))
    assert response.status_code == 200
    row = db.get(EmailOutbox, message_id)
    assert row.status == "bounced"
    assert "mailbox full" in (row.error or "")


def make_closed_trade(db, org_id: str, *, net_pnl: float = 12.5, is_demo: bool = True):
    from app.db.models import Trade

    now = datetime.now(UTC)
    trade = Trade(
        org_id=org_id,
        mode="paper",
        instrument_symbol="R_100",
        side="buy",
        quantity=1,
        entry_price=1000.0,
        exit_price=1000.0 + net_pnl,
        notional=1000.0,
        fees=0.5,
        net_pnl=net_pnl,
        gross_pnl=net_pnl + 0.5,
        entry_reason="test",
        exit_reason="test",
        is_demo=is_demo,
        opened_at=now - timedelta(hours=2),
        closed_at=now - timedelta(hours=1),
    )
    db.add(trade)
    db.commit()
    return trade.id


def test_digest_summarises_trading_activity_once(client, trader, db, monkeypatch):
    from app.core.config import settings
    from app.db.models import EmailOutbox
    from app.services import email as email_service

    monkeypatch.setattr(settings, "email_digest_hour_utc", 0)
    make_closed_trade(db, trader["org_id"], net_pnl=12.5)
    summary = email_service.send_digests(db, now=datetime.now(UTC))
    assert summary["sent"] == 1

    digest = (
        db.query(EmailOutbox)
        .filter(EmailOutbox.to_email == trader["email"], EmailOutbox.template == "trading_digest")
        .one()
    )
    assert "net" in digest.body.lower()
    assert "simulated" in digest.body.lower()
    assert digest.unsubscribe_token

    # The same day does not produce a second digest.
    again = email_service.send_digests(db, now=datetime.now(UTC))
    assert again["sent"] == 0


def test_digest_skips_users_without_activity(client, trader, db, monkeypatch):
    from app.core.config import settings
    from app.db.models import EmailOutbox
    from app.services import email as email_service

    monkeypatch.setattr(settings, "email_digest_hour_utc", 0)
    email_service.send_digests(db, now=datetime.now(UTC))
    assert db.query(EmailOutbox).filter(EmailOutbox.template == "trading_digest").count() == 0


def test_digest_respects_the_preference(client, trader, db, monkeypatch):
    from app.core.config import settings
    from app.db.models import EmailOutbox
    from app.services import email as email_service

    monkeypatch.setattr(settings, "email_digest_hour_utc", 0)
    client.put(f"{BASE}/email/preferences", json={"digest_enabled": False}, headers=trader["headers"])
    make_closed_trade(db, trader["org_id"])
    summary = email_service.send_digests(db, now=datetime.now(UTC))
    assert summary["sent"] == 0
    assert db.query(EmailOutbox).filter(EmailOutbox.template == "trading_digest").count() == 0


def test_campaign_is_queued_for_active_subscribers_and_skips_unsubscribed(client, admin, trader, trader2, db):
    from app.db.models import EmailOutbox, NotificationPreference

    client.get(f"{BASE}/email/preferences", headers=trader2["headers"])
    pref = db.query(NotificationPreference).filter_by(user_id=trader2["user_id"]).one()
    client.post(f"{BASE}/email/unsubscribe", json={"token": pref.unsubscribe_token})

    created = client.post(
        f"{BASE}/admin/email/campaigns",
        json={
            "name": "Spring update",
            "subject": "New strategies are live",
            "template": "announcement",
            "body": "Three new Deriv strategies are available.",
            "audience": "all",
            "send_now": True,
        },
        headers=admin["headers"],
    )
    assert created.status_code == 201, created.text
    campaign = created.json()["campaign"]
    assert campaign["status"] == "scheduled"

    sent = client.post(f"{BASE}/admin/email/campaigns/{campaign['id']}/send", headers=admin["headers"])
    assert sent.status_code == 200, sent.text
    assert sent.json()["campaign"]["status"] == "sent"

    recipients = {
        row.to_email
        for row in db.query(EmailOutbox).filter(EmailOutbox.template == "announcement").all()
    }
    assert trader["email"] in recipients
    assert trader2["email"] not in recipients


def test_campaign_validation_and_permissions(client, admin, trader, db):
    assert client.get(f"{BASE}/admin/email", headers=trader["headers"]).status_code == 404
    assert (
        client.post(
            f"{BASE}/admin/email/campaigns",
            json={"name": "x", "subject": "y", "template": "announcement"},
            headers=trader["headers"],
        ).status_code
        == 404
    )

    unknown = client.post(
        f"{BASE}/admin/email/campaigns",
        json={"name": "Bad template", "subject": "Hi", "template": "nope"},
        headers=admin["headers"],
    )
    assert unknown.status_code == 400
    assert unknown.json()["detail"]["code"] == "unknown_template"

    missing_tier = client.post(
        f"{BASE}/admin/email/campaigns",
        json={"name": "Tier blast", "subject": "Hi", "audience": "tier"},
        headers=admin["headers"],
    )
    assert missing_tier.status_code == 400
    assert missing_tier.json()["detail"]["code"] == "tier_required"


def test_admin_email_centre_reports_honest_provider_state(client, admin):
    body = client.get(f"{BASE}/admin/email", headers=admin["headers"]).json()
    assert body["stats"]["delivery_configured"] is False
    assert body["stats"]["provider"] == "outbox"
    assert "not delivered" in body["stats"]["note"]
    assert "announcement" in body["templates"]


def test_notification_email_respects_preferences(client, trader, db):
    from app.db.models import EmailOutbox
    from app.services import notifications

    notifications.notify(
        db,
        org_id=trader["org_id"],
        user_id=trader["user_id"],
        category="connection",
        title="Connection needs attention",
        body="Deriv rejected the token.",
    )
    db.commit()
    assert db.query(EmailOutbox).filter(EmailOutbox.subject == "Connection needs attention").count() == 1

    client.put(
        f"{BASE}/email/preferences",
        json={"categories": {"connection": False}},
        headers=trader["headers"],
    )
    notifications.notify(
        db,
        org_id=trader["org_id"],
        user_id=trader["user_id"],
        category="connection",
        title="Second connection notice",
        body="Still failing.",
    )
    db.commit()
    assert db.query(EmailOutbox).filter(EmailOutbox.subject == "Second connection notice").count() == 0


def test_security_and_billing_notices_cannot_be_switched_off(client, trader, db):
    from app.db.models import EmailOutbox
    from app.services import notifications

    response = client.put(
        f"{BASE}/email/preferences",
        json={"email_enabled": False, "categories": {"security": False, "billing": False}},
        headers=trader["headers"],
    )
    assert response.status_code == 200
    assert response.json()["preferences"]["categories"]["security"] is True
    assert response.json()["preferences"]["categories"]["billing"] is True

    notifications.notify(
        db,
        org_id=trader["org_id"],
        user_id=trader["user_id"],
        category="security",
        title="Password changed",
        body="Your password was changed.",
    )
    db.commit()
    assert db.query(EmailOutbox).filter(EmailOutbox.subject == "Password changed").count() == 1


def test_trading_notifications_do_not_send_individual_emails(client, trader, db):
    from app.db.models import EmailOutbox
    from app.services import notifications

    notifications.notify(
        db,
        org_id=trader["org_id"],
        user_id=trader["user_id"],
        category="trade",
        title="Position opened",
        body="R_100 buy filled.",
    )
    db.commit()
    assert db.query(EmailOutbox).filter(EmailOutbox.subject == "Position opened").count() == 0
