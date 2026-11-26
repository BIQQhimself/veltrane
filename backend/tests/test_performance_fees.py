from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.conftest import BASE, place_order


def _enable_fees(client, admin, jurisdictions: list[str] | None = None):
    return client.put(
        f"{BASE}/admin/performance-fees/settings",
        json={
            "enabled": True,
            "rate": 0.2,
            "legal_review_completed": True,
            "jurisdictions_allowed": jurisdictions or [],
        },
        headers=admin["headers"],
    )


def test_fees_disabled_by_default(client, elite_trader):
    state = client.get(f"{BASE}/billing/performance-fee", headers=elite_trader["headers"]).json()
    assert state["available"] is True
    assert state["enabled"] is False
    assert state["legal_review_completed"] is False
    assert state["consent"] is None


def test_cannot_enable_without_legal_review(client, admin):
    response = client.put(
        f"{BASE}/admin/performance-fees/settings",
        json={"enabled": True, "rate": 0.2, "legal_review_completed": False, "jurisdictions_allowed": []},
        headers=admin["headers"],
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "legal_review_required"


def test_consent_requires_legal_review_then_records(client, elite_trader, admin):
    blocked = client.post(
        f"{BASE}/billing/performance-fee/consent",
        json={"accepted": True},
        headers=elite_trader["headers"],
    )
    assert blocked.status_code == 400
    assert blocked.json()["detail"]["code"] == "legal_review_required"

    assert _enable_fees(client, admin).status_code == 200

    no_consent = client.post(
        f"{BASE}/billing/performance-fee/consent",
        json={"accepted": False},
        headers=elite_trader["headers"],
    )
    assert no_consent.status_code == 400

    accepted = client.post(
        f"{BASE}/billing/performance-fee/consent",
        json={"accepted": True},
        headers=elite_trader["headers"],
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["fee_rate"] == 0.2

    state = client.get(f"{BASE}/billing/performance-fee", headers=elite_trader["headers"]).json()
    assert state["consent"]["fee_rate"] == 0.2


    assert client.get(f"{BASE}/users/me/audit", headers=elite_trader["headers"]).json()["entries"]


def test_non_elite_cannot_accept_fees(client, pro_trader, admin):
    _enable_fees(client, admin)
    response = client.post(
        f"{BASE}/billing/performance-fee/consent",
        json={"accepted": True},
        headers=pro_trader["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "entitlement_required"


def test_jurisdiction_gate(client, elite_trader, admin):
    _enable_fees(client, admin, jurisdictions=["US"])
    response = client.post(
        f"{BASE}/billing/performance-fee/consent",
        json={"accepted": True},
        headers=elite_trader["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "jurisdiction_not_allowed"


def test_fee_computed_on_realised_pnl_above_high_water_mark(client, elite_trader, admin, db):
    from app.db.models import FeeConsent, Trade

    _enable_fees(client, admin)
    client.post(
        f"{BASE}/billing/performance-fee/consent", json={"accepted": True}, headers=elite_trader["headers"]
    )

    # Generate realised P&L through the real paper-trading path.
    for _ in range(3):
        buy = place_order(client, elite_trader["headers"], quantity=0.01)
        assert buy["body"]["order"]["status"] == "filled"
        position = client.get(f"{BASE}/positions", headers=elite_trader["headers"]).json()["positions"][0]
        close = client.post(
            f"{BASE}/positions/{position['id']}/close",
            json={"reason": "fee test"},
            headers=elite_trader["headers"],
        )
        assert close.status_code == 200

    realised = sum(float(t.net_pnl) for t in db.query(Trade).filter(Trade.org_id == elite_trader["org_id"]).all())
    assert realised != 0

    consent = db.query(FeeConsent).filter(FeeConsent.org_id == elite_trader["org_id"]).one()
    consent.accepted_at = datetime.now(UTC) - timedelta(days=2)
    db.commit()

    period_start = datetime.now(UTC) - timedelta(days=1)
    period_end = datetime.now(UTC) + timedelta(days=1)
    computed = client.post(
        f"{BASE}/admin/performance-fees/compute",
        json={"org_id": elite_trader["org_id"], "period_start": period_start.isoformat(), "period_end": period_end.isoformat()},
        headers=admin["headers"],
    )
    assert computed.status_code == 201, computed.text
    body = computed.json()
    assert body["status"] == "draft"
    expected = max(0.0, realised) * 0.2
    assert abs(body["fee_amount"] - round(expected, 2)) < 0.02
    assert body["calculation"]["realised_pnl_only"] is True
    assert body["calculation"]["unrealised_excluded"] is True

    invoiced = client.post(f"{BASE}/admin/performance-fees/{body['id']}/invoice", headers=admin["headers"])
    assert invoiced.status_code == 200
    assert invoiced.json()["status"] == "invoiced"

    listing = client.get(f"{BASE}/admin/performance-fees", headers=admin["headers"]).json()
    assert listing["records"][0]["status"] == "invoiced"


def test_no_fee_below_high_water_mark(client, elite_trader, admin, db):
    from app.db.models import FeeConsent, HighWaterMark

    _enable_fees(client, admin)
    client.post(
        f"{BASE}/billing/performance-fee/consent", json={"accepted": True}, headers=elite_trader["headers"]
    )
    consent = db.query(FeeConsent).filter(FeeConsent.org_id == elite_trader["org_id"]).one()
    consent.accepted_at = datetime.now(UTC) - timedelta(days=10)
    hwm = HighWaterMark(
        org_id=elite_trader["org_id"], scope="portfolio", value=1_000_000.0, as_of=datetime.now(UTC)
    )
    db.add(hwm)
    db.commit()

    now = datetime.now(UTC)
    computed = client.post(
        f"{BASE}/admin/performance-fees/compute",
        json={"org_id": elite_trader["org_id"], "period_start": (now - timedelta(days=1)).isoformat(), "period_end": now.isoformat()},
        headers=admin["headers"],
    )
    assert computed.status_code == 201
    assert computed.json()["fee_amount"] == 0.0


def test_compute_requires_consent(client, elite_trader, admin):
    _enable_fees(client, admin)
    now = datetime.now(UTC)
    response = client.post(
        f"{BASE}/admin/performance-fees/compute",
        json={"org_id": elite_trader["org_id"], "period_start": (now - timedelta(days=1)).isoformat(), "period_end": now.isoformat()},
        headers=admin["headers"],
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "consent_missing"


def test_compute_blocked_when_disabled(client, elite_trader, admin):
    now = datetime.now(UTC)
    response = client.post(
        f"{BASE}/admin/performance-fees/compute",
        json={"org_id": elite_trader["org_id"], "period_start": (now - timedelta(days=1)).isoformat(), "period_end": now.isoformat()},
        headers=admin["headers"],
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "performance_fees_disabled"
