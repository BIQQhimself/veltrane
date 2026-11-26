from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC

from app.services.billing import _mock_secret
from tests.conftest import BASE


def signed_headers(body: bytes) -> dict[str, str]:
    ts = str(int(time.time()))
    sig = hmac.new(_mock_secret(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return {"X-Mock-Timestamp": ts, "X-Mock-Signature": sig, "Content-Type": "application/json"}


def send_event(client, event: dict, tamper: bool = False):
    body = json.dumps(event).encode()
    headers = signed_headers(body)
    if tamper:
        body = body.replace(b'"amount_total": 4900', b'"amount_total": 100')
    return client.post(f"{BASE}/webhooks/billing/mock", content=body, headers=headers)


def checkout_event(org_id: str, plan_code: str = "pro", amount_cents: int = 4900) -> dict:
    return {
        "id": f"evt_{uuid.uuid4().hex[:12]}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_{uuid.uuid4().hex[:8]}",
                "amount_total": amount_cents,
                "currency": "usd",
                "subscription": f"sub_{uuid.uuid4().hex[:8]}",
                "metadata": {"org_id": org_id, "plan_code": plan_code},
            }
        },
    }


def test_plan_catalog_matches_brief(client):
    plans = client.get(f"{BASE}/plans").json()["plans"]
    by_code = {p["code"]: p for p in plans}
    assert by_code["free"]["price_monthly"] == 0
    assert by_code["basic"]["price_monthly"] == 19
    assert by_code["pro"]["price_monthly"] == 49
    assert by_code["elite"]["price_monthly"] == 149
    assert "no real-money execution" in " ".join(by_code["free"]["features"]).lower()
    assert by_code["elite"]["limits"]["max_connections"] > by_code["pro"]["limits"]["max_connections"]
    assert by_code["pro"]["limits"]["backtesting"] is True
    assert by_code["free"]["limits"]["backtesting"] is False


def test_checkout_requires_signed_webhook_before_activation(client, trader, db):
    checkout = client.post(f"{BASE}/billing/checkout", json={"plan_code": "pro"}, headers=trader["headers"])
    assert checkout.status_code == 200
    body = checkout.json()
    assert body["mode"] == "mock"

    # A frontend "success" alone must not activate anything.
    sub = client.get(f"{BASE}/billing/subscription", headers=trader["headers"]).json()
    assert sub["effective_plan_code"] == "free"

    event = checkout_event(trader["org_id"], "pro")
    tampered = send_event(client, event, tamper=True)
    assert tampered.status_code == 400
    assert tampered.json()["detail"]["code"] == "invalid_signature"

    accepted = send_event(client, event)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "processed"

    sub = client.get(f"{BASE}/billing/subscription", headers=trader["headers"]).json()
    assert sub["effective_plan_code"] == "pro"
    # The mock checkout collects payment for the first period, so the subscription
    # starts active rather than in a trial that would contradict the paid invoice.
    assert sub["subscription"]["status"] == "active"
    assert sub["subscription"]["trial_end"] is None
    assert sub["entitlements"]["limits"]["max_connections"] == 8


def test_webhook_replay_is_idempotent(client, trader, db):
    event = checkout_event(trader["org_id"], "pro")
    first = send_event(client, event)
    second = send_event(client, event)
    assert first.json()["status"] == "processed"
    assert second.json()["status"] == "already_processed"

    from app.db.models import Payment

    payments = db.query(Payment).filter(Payment.org_id == trader["org_id"]).all()
    assert len(payments) == 1


def test_payment_failure_sets_past_due_and_notifies(client, trader, db):
    send_event(client, checkout_event(trader["org_id"], "pro"))
    event = {
        "id": f"evt_{uuid.uuid4().hex[:12]}",
        "type": "invoice.payment_failed",
        "data": {"object": {"id": "in_1", "metadata": {"org_id": trader["org_id"]}}},
    }
    response = send_event(client, event)
    assert response.status_code == 200

    sub = client.get(f"{BASE}/billing/subscription", headers=trader["headers"]).json()
    assert sub["subscription"]["status"] == "past_due"

    notes = client.get(f"{BASE}/notifications", headers=trader["headers"]).json()["notifications"]
    assert any("Payment failed" in n["title"] for n in notes)


def test_cancellation_reverts_to_free(client, trader):
    send_event(client, checkout_event(trader["org_id"], "pro"))
    response = client.post(f"{BASE}/billing/cancel", json={"immediate": True}, headers=trader["headers"])
    assert response.status_code == 200
    sub = client.get(f"{BASE}/billing/subscription", headers=trader["headers"]).json()
    assert sub["effective_plan_code"] == "free"


def test_cancel_at_period_end_keeps_entitlements(client, trader):
    send_event(client, checkout_event(trader["org_id"], "pro"))
    response = client.post(f"{BASE}/billing/cancel", json={"immediate": False}, headers=trader["headers"])
    assert response.json()["cancel_at_period_end"] is True
    sub = client.get(f"{BASE}/billing/subscription", headers=trader["headers"]).json()
    assert sub["effective_plan_code"] == "pro"
    assert sub["subscription"]["cancel_at_period_end"] is True


def test_change_plan_upgrade_and_downgrade(client, trader, db):
    send_event(client, checkout_event(trader["org_id"], "basic", amount_cents=1900))
    upgrade = client.post(f"{BASE}/billing/change-plan", json={"plan_code": "elite"}, headers=trader["headers"])
    assert upgrade.status_code == 200, upgrade.text
    assert upgrade.json()["mode"] == "scheduled"
    # Paid-to-paid changes take effect at renewal; no silent proration or mid-cycle upsell.
    assert client.get(f"{BASE}/auth/me", headers=trader["headers"]).json()["entitlements"]["plan_code"] == "basic"

    renewal = {
        "id": f"evt_{uuid.uuid4().hex[:12]}",
        "type": "invoice.payment_succeeded",
        "data": {
            "object": {
                "id": f"in_{uuid.uuid4().hex[:8]}",
                "amount_paid": 14900,
                "currency": "usd",
                "metadata": {"org_id": trader["org_id"]},
            }
        },
    }
    # Bring the renewal date forward instead of waiting seven trial days.
    from datetime import datetime, timedelta

    from app.db.models import Subscription

    sub = db.query(Subscription).filter(Subscription.org_id == trader["org_id"]).one()
    sub.pending_effective_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    assert send_event(client, renewal).status_code == 200
    assert client.get(f"{BASE}/auth/me", headers=trader["headers"]).json()["entitlements"]["plan_code"] == "elite"

    downgrade = client.post(f"{BASE}/billing/change-plan", json={"plan_code": "basic"}, headers=trader["headers"])
    assert downgrade.status_code == 200
    assert downgrade.json()["mode"] == "scheduled"


def test_invoices_and_payments_listed(client, trader):
    send_event(client, checkout_event(trader["org_id"], "pro"))
    payments = client.get(f"{BASE}/billing/payments", headers=trader["headers"]).json()
    assert payments["payments"]
    assert payments["payments"][0]["amount"] == 49.0
    invoices = client.get(f"{BASE}/billing/invoices", headers=trader["headers"]).json()
    assert invoices["invoices"][0]["total"] == 49.0


def test_refund_requires_admin_and_cannot_exceed_payment(client, trader, admin, db):
    send_event(client, checkout_event(trader["org_id"], "pro"))
    payment = client.get(f"{BASE}/billing/payments", headers=trader["headers"]).json()["payments"][0]

    forbidden = client.post(
        f"{BASE}/admin/refunds",
        json={"payment_id": payment["id"], "amount": 10, "reason": "customer request"},
        headers=trader["headers"],
    )
    assert forbidden.status_code == 404  # staff surface is not disclosed to members

    too_much = client.post(
        f"{BASE}/admin/refunds",
        json={"payment_id": payment["id"], "amount": 500, "reason": "customer request"},
        headers=admin["headers"],
    )
    assert too_much.status_code == 400

    ok = client.post(
        f"{BASE}/admin/refunds",
        json={"payment_id": payment["id"], "amount": 20, "reason": "goodwill"},
        headers=admin["headers"],
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["amount"] == 20.0


def test_webhook_for_unknown_org_is_rejected(client):
    event = checkout_event(str(uuid.uuid4()), "pro")
    response = send_event(client, event)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "webhook_processing_failed"


def test_stripe_signature_verification_unit():
    from app.services.billing import verify_stripe_signature

    assert verify_stripe_signature(b"{}", None) is False
    assert verify_stripe_signature(b"{}", "t=1,v1=deadbeef") is False
