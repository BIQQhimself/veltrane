"""Deriv referral programme: redirect, click recording, attribution and admin reporting."""

from __future__ import annotations

import uuid

from tests.conftest import BASE


def test_referral_redirect_records_one_click_per_visitor(client, db):
    from app.db.models import ReferralEvent

    first = client.get(f"{BASE}/referrals/deriv", params={"v": "visitor-ref0001"}, follow_redirects=False)
    assert first.status_code == 302
    assert first.headers["location"].startswith("https://t.deriv.link")
    assert "t=XXSKPY9YLQB2" in first.headers["location"]

    # A refresh must not inflate the funnel.
    client.get(f"{BASE}/referrals/deriv", params={"v": "visitor-ref0001"}, follow_redirects=False)
    clicks = (
        db.query(ReferralEvent)
        .filter(ReferralEvent.kind == "click", ReferralEvent.visitor_id == "visitor-ref0001")
        .count()
    )
    assert clicks == 1


def test_referral_redirect_sends_visitors_to_signup_when_link_disabled(client, admin, db):
    from app.core.config import settings

    client.put(
        f"{BASE}/admin/referrals/link",
        json={"url": "", "campaign": "veltrane", "enabled": False},
        headers=admin["headers"],
    )
    response = client.get(f"{BASE}/referrals/deriv", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].rstrip("/").endswith("/register")
    assert settings.web_base_url.split("//")[1].split("/")[0] in response.headers["location"]


def test_click_rejects_non_opaque_visitor_ids(client, db):
    from app.db.models import ReferralEvent

    response = client.post(
        f"{BASE}/referrals/click", json={"visitor_id": "<script>alert(1)</script>", "landing": "pricing"}
    )
    assert response.status_code == 200
    event = db.get(ReferralEvent, response.json()["event_id"])
    # The supplied value is not an opaque id, so a generated one is stored instead.
    assert event.visitor_id.startswith("anon-")
    assert "<script>" not in event.visitor_id


def test_registration_is_attributed_to_the_click(client, db):
    from app.db.models import ReferralEvent

    client.get(f"{BASE}/referrals/deriv", params={"v": "visitor-reg00001"}, follow_redirects=False)
    email = f"referred-{uuid.uuid4().hex[:8]}@example.com"
    response = client.post(
        f"{BASE}/auth/register",
        json={
            "email": email,
            "password": "Veltrane!Test2026",
            "full_name": "Referred Trader",
            "accept_terms": True,
            "referral_visitor_id": "visitor-reg00001",
        },
    )
    assert response.status_code == 201, response.text
    event = (
        db.query(ReferralEvent)
        .filter(ReferralEvent.kind == "registration", ReferralEvent.visitor_id == "visitor-reg00001")
        .one()
    )
    assert event.meta["attributed"] is True
    assert event.user_id == response.json()["user"]["id"]


def test_referral_config_is_public_but_minimal(client):
    body = client.get(f"{BASE}/referrals/config").json()
    assert body["enabled"] is True
    assert body["url"].startswith("https://t.deriv.link")
    assert "token" not in body


def test_admin_referral_overview_and_link_validation(client, admin):
    overview = client.get(f"{BASE}/admin/referrals", headers=admin["headers"])
    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert {"clicks", "registrations", "connections", "verified_commission"} <= set(body["funnel"])
    assert body["link"]["token"] == "XXSKPY9YLQB2"

    insecure = client.put(
        f"{BASE}/admin/referrals/link",
        json={"url": "http://t.deriv.link/?t=XXSKPY9YLQB2", "campaign": "veltrane", "enabled": True},
        headers=admin["headers"],
    )
    assert insecure.status_code == 400

    untracked = client.put(
        f"{BASE}/admin/referrals/link",
        json={"url": "https://t.deriv.link/", "campaign": "veltrane", "enabled": True},
        headers=admin["headers"],
    )
    assert untracked.status_code == 400
    assert untracked.json()["detail"]["code"] == "invalid_referral_link"

    updated = client.put(
        f"{BASE}/admin/referrals/link",
        json={"url": "https://t.deriv.link/?t=OTHERCAMPAIGN1", "campaign": "spring", "enabled": True},
        headers=admin["headers"],
    )
    assert updated.status_code == 200
    assert updated.json()["link"]["token"] == "OTHERCAMPAIGN1"


def test_subscribers_cannot_reach_admin_referrals(client, trader):
    # The admin surface answers 404 to non-staff so it cannot be probed for existence.
    assert client.get(f"{BASE}/admin/referrals", headers=trader["headers"]).status_code == 404
    assert (
        client.post(
            f"{BASE}/admin/referrals/conversions",
            json={"user_id": trader["user_id"], "amount": 10},
            headers=trader["headers"],
        ).status_code
        == 404
    )


def test_verified_conversion_is_only_counted_when_recorded(client, admin, trader):
    before = client.get(f"{BASE}/admin/referrals", headers=admin["headers"]).json()["funnel"]
    assert before["verified_commission"] == 0

    recorded = client.post(
        f"{BASE}/admin/referrals/conversions",
        json={"user_id": trader["user_id"], "amount": 42.5, "currency": "USD", "note": "Deriv partner statement"},
        headers=admin["headers"],
    )
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["verified"] is True

    after = client.get(f"{BASE}/admin/referrals", headers=admin["headers"]).json()["funnel"]
    assert after["verified_commission"] == 42.5
    assert after["verified_conversions"] == 1


def test_user_sees_their_own_referral_status_only(client, trader):
    body = client.get(f"{BASE}/referrals/me", headers=trader["headers"]).json()
    assert body["link"].startswith("https://t.deriv.link")
    assert "verified_commission" not in body
    assert isinstance(body["events"], list)
