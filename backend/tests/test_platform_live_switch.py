from __future__ import annotations

from app.core.config import Settings
from app.db.models import SystemSetting
from app.services import platform_switch
from tests.conftest import BASE


def test_staff_key_defaults_to_operator_flag(db):
    assert platform_switch.staff_enabled(db) is True


def test_effective_requires_both_keys(db, monkeypatch, make_user):
    monkeypatch.setattr(platform_switch.settings, "live_trading_enabled", True)
    assert platform_switch.effective(db) is True

    staff = _staff_user(db, make_user("owner"))
    platform_switch.set_staff(db, user=staff, enabled=False, reason="deployment prep")
    assert platform_switch.staff_enabled(db) is False
    assert platform_switch.effective(db) is False

    monkeypatch.setattr(platform_switch.settings, "live_trading_enabled", False)
    platform_switch.set_staff(db, user=staff, enabled=True, reason="re-arm staff key")
    assert platform_switch.effective(db) is False


def _staff_user(db, account):
    from app.db.models import User

    user = db.get(User, account["user_id"])
    user.is_staff = True
    user.staff_role = "owner"
    db.commit()
    return user


def test_member_cannot_read_or_write_switch(client, trader):
    assert client.get(f"{BASE}/admin/live-trading", headers=trader["headers"]).status_code == 404
    response = client.put(
        f"{BASE}/admin/live-trading",
        headers=trader["headers"],
        json={"enabled": True, "reason": "member attempt", "confirm": "ENABLE LIVE TRADING"},
    )
    assert response.status_code == 404


def test_admin_switch_requires_typed_confirmation(client, admin, db):
    response = client.put(
        f"{BASE}/admin/live-trading",
        headers=admin["headers"],
        json={"enabled": False, "reason": "routine halt", "confirm": "yes"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "confirmation_mismatch"
    assert db.get(SystemSetting, platform_switch.SETTING_KEY) is None


def test_admin_cannot_enable_while_deployment_flag_off(client, admin, monkeypatch):
    monkeypatch.setattr(platform_switch.settings, "live_trading_enabled", False)
    response = client.put(
        f"{BASE}/admin/live-trading",
        headers=admin["headers"],
        json={"enabled": True, "reason": "attempt without operator key", "confirm": "ENABLE LIVE TRADING"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "deployment_flag_off"


def test_admin_can_disable_and_state_is_reported(client, admin, db, monkeypatch):
    monkeypatch.setattr(platform_switch.settings, "live_trading_enabled", True)
    response = client.put(
        f"{BASE}/admin/live-trading",
        headers=admin["headers"],
        json={"enabled": False, "reason": "stop all live execution", "confirm": "DISABLE LIVE TRADING"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["staff_enabled"] is False
    assert body["deployment_enabled"] is True
    assert body["effective"] is False

    listed = client.get(f"{BASE}/admin/live-trading", headers=admin["headers"])
    assert listed.status_code == 200
    assert listed.json()["effective"] is False

    state = client.get(f"{BASE}/trading/state", headers=admin["headers"]).json()
    assert state["platform_live_enabled"] is False

    # The audit trail records who flipped it and why.
    from app.db.models import AuditLog

    row = db.query(AuditLog).filter(AuditLog.action == "admin.live_trading_switch").first()
    assert row is not None
    assert "stop all live execution" in str(row.meta)


def test_trusted_proxy_matching():
    settings = Settings(
        env="test",
        secret_key="test-secret-key-0123456789abcdef0123456789abcdef",
        trusted_proxies="10.0.0.0/8, 203.0.113.9",
    )
    assert settings.is_trusted_proxy("10.4.5.6") is True
    assert settings.is_trusted_proxy("203.0.113.9") is True
    assert settings.is_trusted_proxy("203.0.113.10") is False
    assert settings.is_trusted_proxy("not-an-ip") is False

    wide = Settings(
        env="test",
        secret_key="test-secret-key-0123456789abcdef0123456789abcdef",
        trusted_proxies="*",
    )
    assert wide.is_trusted_proxy("198.51.100.7") is True


def test_forwarded_header_ignored_from_untrusted_peer(monkeypatch):
    from app.core import rate_limit
    from starlette.requests import Request

    monkeypatch.setattr(rate_limit.settings, "trusted_proxies", "10.0.0.0/8")

    def request(peer: str, forwarded: str) -> Request:
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(b"x-forwarded-for", forwarded.encode())],
                "client": (peer, 1234),
            }
        )

    # Peer outside the trusted range: the header cannot be used to pick a bucket.
    assert rate_limit.client_ip(request("198.51.100.7", "1.2.3.4")) == "198.51.100.7"
    # Peer inside the trusted range: the real client address is used.
    assert rate_limit.client_ip(request("10.0.1.5", "1.2.3.4")) == "1.2.3.4"


def test_libpq_database_urls_are_mapped_to_psycopg(tmp_path):
    from app.core.config import Settings

    base = {"env": "test", "secret_key": "test-secret-key-0123456789abcdef0123456789abcdef"}
    for given in (
        "postgres://user:pw@db.internal:5432/veltrane",
        "postgresql://user:pw@db.internal:5432/veltrane",
        "postgresql+psycopg://user:pw@db.internal:5432/veltrane",
    ):
        settings = Settings(database_url=given, **base)
        assert settings.database_url == "postgresql+psycopg://user:pw@db.internal:5432/veltrane", given
