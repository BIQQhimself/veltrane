"""The one-minute floor and the runtime visual identity.

Two behaviours the redesign depends on:

* No contract shorter than a minute can be quoted or opened, whatever the client sends,
  and the refusal names the reason instead of reporting a generic validation error.
* An administrator can change the platform palette and branding at runtime, and the
  public theme endpoint reflects it immediately — the browser never needs a new build.
"""

from __future__ import annotations

from app.trading import binary as binary_engine

BASE = "/api/v1"


def _auth(trader) -> dict:
    return trader["headers"]


# --------------------------------------------------------------- duration floor
def test_sub_minute_durations_are_refused_by_the_request_schema(client, trader):
    for seconds in (1, 30, 59):
        response = client.post(
            f"{BASE}/binary/quote",
            headers=_auth(trader),
            json={"symbol": "BTC/USDT", "duration_seconds": seconds},
        )
        assert response.status_code == 422, response.text
        errors = response.json()["detail"]["details"]["errors"]
        assert errors[0]["loc"] == ["body", "duration_seconds"]

        response = client.post(
            f"{BASE}/binary/contracts",
            headers=_auth(trader),
            json={"symbol": "BTC/USDT", "direction": "call", "stake": 10, "duration_seconds": seconds},
        )
        assert response.status_code == 422, response.text


def test_one_minute_is_the_shortest_accepted_duration(client, trader):
    quote = client.post(
        f"{BASE}/binary/quote",
        headers=_auth(trader),
        json={"symbol": "BTC/USDT", "duration_seconds": 60},
    )
    assert quote.status_code == 200, quote.text
    assert quote.json()["duration_seconds"] == 60
    assert quote.json()["min_duration_seconds"] == 60


def test_engine_refuses_a_too_short_duration_with_a_named_reason():
    from app.core.errors import AppError

    for seconds in (0, -30, 30, 59):
        try:
            binary_engine.validate_duration(seconds)
        except AppError as exc:
            assert exc.detail["code"] == "duration_too_short", exc.detail
        else:  # pragma: no cover - the assertion below is the failure message
            raise AssertionError(f"{seconds}s should not be accepted")


def test_durations_above_the_floor_still_follow_the_offered_options():
    from app.core.errors import AppError

    assert binary_engine.validate_duration(60) == 60
    assert binary_engine.validate_duration(300) == 300
    assert binary_engine.validate_duration(3600) == 3600
    # 90s clears the floor but is not an offered term.
    try:
        binary_engine.validate_duration(90)
    except AppError as exc:
        assert exc.detail["code"] == "invalid_duration"
    else:  # pragma: no cover
        raise AssertionError("90s should not be an offered duration")


def test_assets_endpoint_advertises_the_floor(client):
    response = client.get(f"{BASE}/binary/assets")
    assert response.status_code == 200
    body = response.json()
    assert body["min_duration_seconds"] == 60
    assert min(body["durations"]) >= 60


def test_autonomous_trading_configuration_is_untouched():
    """The floor belongs to the manual contract book, not the Deriv autotrade runner."""
    from app.services import autotrade

    # Autotrade expresses its term in the venue's own unit; it must not be clamped to
    # the binary book's option list.
    assert hasattr(autotrade, "evaluate_entry")
    assert "MIN_DURATION_SECONDS" not in autotrade.__dict__


# ------------------------------------------------------------- runtime identity
def test_theme_endpoint_is_public_and_returns_every_token(client):
    response = client.get(f"{BASE}/theme")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "default"
    assert set(body["colors"]) >= {"background", "surface", "primary", "chart_up", "chart_down"}
    assert body["branding"]["product_name"] == "VELTRANE"


def test_admin_can_change_colours_and_the_public_endpoint_reflects_it(client, admin):
    response = client.put(
        f"{BASE}/admin/theme",
        headers=admin["headers"],
        json={"colors": {"primary": "#123456", "chart_up": "#00ff88"}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["theme"]["colors"]["primary"] == "#123456"

    public = client.get(f"{BASE}/theme").json()
    assert public["source"] == "admin"
    assert public["colors"]["primary"] == "#123456"
    assert public["colors"]["chart_up"] == "#00ff88"
    # Untouched tokens keep their defaults rather than disappearing.
    assert public["colors"]["background"] == "#04060a"


def test_admin_can_change_branding(client, admin):
    response = client.put(
        f"{BASE}/admin/theme",
        headers=admin["headers"],
        json={"branding": {"product_name": "VELTRANE PRO", "logo_mark": "VP"}},
    )
    assert response.status_code == 200, response.text
    public = client.get(f"{BASE}/theme").json()
    assert public["branding"]["product_name"] == "VELTRANE PRO"
    assert public["branding"]["logo_mark"] == "VP"


def test_theme_rejects_values_that_are_not_colours(client, admin):
    for bad in ("red", "#12345", "javascript:alert(1)", "#1234567", ""):
        response = client.put(
            f"{BASE}/admin/theme",
            headers=admin["headers"],
            json={"colors": {"primary": bad}},
        )
        assert response.status_code == 400, (bad, response.text)
        assert response.json()["detail"]["code"] == "invalid_theme"


def test_theme_rejects_unknown_tokens_and_branding_keys(client, admin):
    response = client.put(
        f"{BASE}/admin/theme",
        headers=admin["headers"],
        json={"colors": {"background_image": "#123456"}},
    )
    assert response.status_code == 400
    response = client.put(
        f"{BASE}/admin/theme",
        headers=admin["headers"],
        json={"branding": {"custom_css": "body{}"}},
    )
    assert response.status_code == 400


def test_reset_returns_the_shipped_palette(client, admin):
    client.put(f"{BASE}/admin/theme", headers=admin["headers"], json={"colors": {"primary": "#123456"}})
    response = client.put(f"{BASE}/admin/theme", headers=admin["headers"], json={"reset": True})
    assert response.status_code == 200
    assert response.json()["theme"]["source"] == "default"
    assert client.get(f"{BASE}/theme").json()["colors"]["primary"] == "#2e7bff"


def test_theme_changes_are_audited(client, admin, db):
    from app.db.models import AuditLog

    client.put(f"{BASE}/admin/theme", headers=admin["headers"], json={"colors": {"primary": "#abcdef"}})
    entry = (
        db.query(AuditLog)
        .filter(AuditLog.target_type == "theme")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert entry is not None
    assert entry.actor_email == admin["email"]


def test_subscribers_cannot_change_the_theme(client, trader):
    response = client.put(f"{BASE}/admin/theme", headers=_auth(trader), json={"colors": {"primary": "#abcdef"}})
    assert response.status_code in (403, 404)
    assert client.get(f"{BASE}/theme").json()["colors"]["primary"] == "#2e7bff"
