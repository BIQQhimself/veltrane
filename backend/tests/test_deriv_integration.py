"""End-to-end Deriv integration through the API, against a protocol-faithful local server.

No real money and no real Deriv account: the API talks to ``tests/support/deriv_mock.py``, which
implements the documented REST + WebSocket shapes. The code under test is the production code —
gate, risk engine, session manager, adapter, persistence and serialisation.
"""

from __future__ import annotations

import pytest
from app.core.config import settings
from app.db.models import AutoTradeConfig, AutoTradeSignal, Connection, User
from app.db.session import SessionLocal
from app.services import deriv_sessions, kill_switch

BASE = "/api/v1"


def _connect(client, trader, *, environment="live", account_id="VRTC900001", token=None, app_id=None):
    body = {
        "provider": "deriv",
        "label": f"Deriv {account_id}",
        "environment": environment,
        "api_key": token if token is not None else "pat_test_token_0123456789abcdef",
        "app_id": app_id if app_id is not None else "12345",
        "account_id": account_id,
    }
    return client.post(f"{BASE}/connections", json=body, headers=trader["headers"])


# ------------------------------------------------------------------ connection
def test_pat_connection_is_verified_and_stores_identity(client, trader, deriv_env):
    response = _connect(client, trader)
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["provider"] == "deriv"
    assert body["status"] == "connected"
    assert body["provider_account_id"] == "VRTC900001"
    assert body["provider_account_type"] == "demo"
    assert body["provider_currency"] == "USD"
    assert len(body["provider_meta"]["accounts"]) == 2
    assert body["permissions"]["withdrawal_scope"] == "not_requested"
    # The token must never appear in any response.
    assert deriv_env.state.token not in response.text


def test_connection_with_a_bad_token_is_rejected(client, trader, deriv_env):
    deriv_env.state.reject_token = True
    response = _connect(client, trader)

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "deriv_invalid_token"


def test_connection_requires_an_app_id_when_no_platform_default(client, trader, deriv_env, monkeypatch):
    monkeypatch.setattr(settings, "deriv_app_id", "")
    response = _connect(client, trader, app_id="")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "app_id_required"


def test_unknown_account_is_rejected(client, trader, deriv_env):
    response = _connect(client, trader, account_id="VRTC000000")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "account_not_found"


def test_api_secret_is_not_required_for_deriv(client, trader, deriv_env):
    response = _connect(client, trader)
    assert response.status_code == 201, response.text
    assert "api_secret" not in response.text


# ------------------------------------------------------------------ status and pricing
def test_status_reports_venue_identity_and_gate(client, trader, deriv_env):
    connection_id = _connect(client, trader).json()["id"]

    response = client.get(f"{BASE}/deriv/connections/{connection_id}/status", headers=trader["headers"])
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["connection"]["account_type"] == "demo"
    assert body["connection"]["is_demo"] is True
    assert body["gate"]["allowed"] is True
    assert body["gate"]["scope"] == "demo"
    checks = {c["check"]: c["ok"] for c in body["gate"]["checks"]}
    assert checks["kill_switch"] is True
    assert checks["trade_permission"] is True
    # A venue demo account does not need the platform live switch.
    assert "platform_live_switch" not in checks


def test_preview_prices_a_contract(client, trader, deriv_env):
    connection_id = _connect(client, trader).json()["id"]

    response = client.post(
        f"{BASE}/deriv/connections/{connection_id}/preview",
        json={"symbol": "R_100", "side": "buy", "stake": 10, "duration": 60},
        headers=trader["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["proposal"]["id"]
    assert body["terms"]["payout_pct"] > 0
    assert body["is_demo"] is True


def test_symbols_and_candles_come_from_the_venue(client, trader, deriv_env):
    symbols = client.get(f"{BASE}/deriv/symbols?refresh=true", headers=trader["headers"])
    assert symbols.status_code == 200
    assert "synthetic_index" in symbols.json()["markets"]

    candles = client.get(f"{BASE}/deriv/candles?symbol=R_100&timeframe=1m&limit=5", headers=trader["headers"])
    assert candles.status_code == 200
    assert len(candles.json()["candles"]) == 5


# ------------------------------------------------------------------ execution
def test_demo_contract_opens_and_is_fully_auditable(client, trader, deriv_env):
    connection_id = _connect(client, trader).json()["id"]

    response = client.post(
        f"{BASE}/deriv/connections/{connection_id}/contracts",
        json={"symbol": "R_100", "side": "buy", "stake": 10, "duration": 60},
        headers=trader["headers"],
    )
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["approved"] is True, body["risk"]
    order = body["order"]
    assert order["status"] == "filled"
    assert order["is_demo"] is True
    assert order["provider_order_id"]
    assert order["meta"]["contract_id"] == order["provider_order_id"]
    assert order["meta"]["stake"] == 10.0
    assert body["venue"]["is_demo"] is True

    risk = body["risk"]
    assert risk["decision"] == "approved"
    assert any(c["code"] == "mode_authorization" and c["passed"] for c in risk["checks"])

    detail = client.get(f"{BASE}/deriv/trades/{order['id']}", headers=trader["headers"])
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["order"]["provider_order_id"] == order["provider_order_id"]
    assert payload["risk"]["checks"], "every trade must show the risk checks that ran"


def test_duplicate_contract_is_blocked(client, trader, deriv_env):
    connection_id = _connect(client, trader).json()["id"]
    body = {"symbol": "R_100", "side": "buy", "stake": 10, "duration": 60}

    first = client.post(f"{BASE}/deriv/connections/{connection_id}/contracts", json=body, headers=trader["headers"])
    assert first.status_code == 201, first.text
    second = client.post(f"{BASE}/deriv/connections/{connection_id}/contracts", json=body, headers=trader["headers"])
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "duplicate_order"


def test_free_account_demo_contracts_count_against_the_daily_cap(client, trader, deriv_env):
    """A venue demo account is simulated money: five contracts a day on Free, then a refusal."""
    connection_id = _connect(client, trader).json()["id"]
    stakes = [10, 11, 12, 13, 14]
    for stake in stakes:
        body = {"symbol": "R_100", "side": "buy", "stake": stake, "duration": 60}
        ok = client.post(f"{BASE}/deriv/connections/{connection_id}/contracts", json=body, headers=trader["headers"])
        assert ok.status_code == 201, ok.text
        assert ok.json()["approved"] is True, ok.json().get("risk")

    sixth = client.post(
        f"{BASE}/deriv/connections/{connection_id}/contracts",
        json={"symbol": "R_100", "side": "buy", "stake": 15, "duration": 60},
        headers=trader["headers"],
    )
    assert sixth.status_code == 201, sixth.text
    assert sixth.json()["approved"] is False
    codes = [f["code"] for f in sixth.json()["risk"]["failed_rules"]]
    assert "demo_execution_limit" in codes
    assert deriv_env.state.contracts  # the five demo contracts really were placed


def test_distinct_contract_terms_are_not_treated_as_duplicates(client, trader, deriv_env):
    """Same underlying, different stake: a second, legitimate order that the engine must price."""
    connection_id = _connect(client, trader).json()["id"]
    first = client.post(
        f"{BASE}/deriv/connections/{connection_id}/contracts",
        json={"symbol": "R_100", "side": "buy", "stake": 10, "duration": 60},
        headers=trader["headers"],
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"{BASE}/deriv/connections/{connection_id}/contracts",
        json={"symbol": "R_100", "side": "buy", "stake": 12, "duration": 60},
        headers=trader["headers"],
    )
    assert second.status_code == 201, second.text
    assert second.json()["approved"] is True


def test_idempotency_key_replays_the_same_order(client, trader, deriv_env):
    connection_id = _connect(client, trader).json()["id"]
    body = {
        "symbol": "R_100",
        "side": "buy",
        "stake": 10,
        "duration": 60,
        "idempotency_key": "qa-idem-1",
    }
    first = client.post(f"{BASE}/deriv/connections/{connection_id}/contracts", json=body, headers=trader["headers"])
    assert first.status_code == 201, first.text
    replay = client.post(f"{BASE}/deriv/connections/{connection_id}/contracts", json=body, headers=trader["headers"])
    assert replay.status_code == 201
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["order"]["id"] == first.json()["order"]["id"]


def test_read_only_connection_cannot_execute(client, trader, deriv_env):
    connection_id = _connect(client, trader, environment="read_only").json()["id"]

    response = client.post(
        f"{BASE}/deriv/connections/{connection_id}/contracts",
        json={"symbol": "R_100", "side": "buy", "stake": 10, "duration": 60},
        headers=trader["headers"],
    )
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["code"] == "execution_blocked"
    assert any(c["check"] == "trade_permission" and not c["ok"] for c in body["detail"]["details"]["gate"]["checks"])


def test_kill_switch_blocks_execution(client, trader, deriv_env, db):
    connection_id = _connect(client, trader).json()["id"]

    kill_switch.engage(db, scope="org", target=trader["org_id"], actor=None, reason="qa")
    db.commit()
    try:
        blocked = client.post(
            f"{BASE}/deriv/connections/{connection_id}/contracts",
            json={"symbol": "R_100", "side": "buy", "stake": 10, "duration": 60},
            headers=trader["headers"],
        )
        assert blocked.status_code == 400
        assert blocked.json()["detail"]["code"] == "execution_blocked"
    finally:
        kill_switch.release(db, scope="org", target=trader["org_id"], actor=None, reason="qa-done")
        db.commit()

    allowed = client.post(
        f"{BASE}/deriv/connections/{connection_id}/contracts",
        json={"symbol": "R_100", "side": "buy", "stake": 10, "duration": 60},
        headers=trader["headers"],
    )
    assert allowed.status_code == 201, allowed.text


def test_real_account_is_blocked_while_the_platform_flag_is_off(client, trader, deriv_env):
    connection_id = _connect(client, trader, account_id="CR700001").json()["id"]

    response = client.post(
        f"{BASE}/deriv/connections/{connection_id}/contracts",
        json={"symbol": "R_100", "side": "buy", "stake": 10, "duration": 60},
        headers=trader["headers"],
    )
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["code"] == "execution_blocked"
    failed = {c["check"] for c in body["detail"]["details"]["gate"]["checks"] if not c["ok"]}
    assert "platform_live_switch" in failed
    assert "live_authorisation" in failed


def test_contracts_sync_and_close(client, trader, deriv_env, db):
    connection_id = _connect(client, trader).json()["id"]
    opened = client.post(
        f"{BASE}/deriv/connections/{connection_id}/contracts",
        json={"symbol": "R_100", "side": "buy", "stake": 10, "duration": 60},
        headers=trader["headers"],
    )
    assert opened.status_code == 201, opened.text
    contract_id = opened.json()["order"]["provider_order_id"]

    synced = client.get(f"{BASE}/deriv/connections/{connection_id}/contracts", headers=trader["headers"])
    assert synced.status_code == 200
    assert synced.json()["open_contracts"] == 1

    closed = client.post(
        f"{BASE}/deriv/connections/{connection_id}/contracts/{contract_id}/close",
        headers=trader["headers"],
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "sold"
    assert closed.json()["sold_for"] > 0

    # An early exit realises P&L immediately: neither the order nor its position may stay open
    # waiting for reconciliation, and the realised figure must be sold_for minus stake.
    from app.db.models import Order, Position

    order = db.query(Order).filter(Order.provider_order_id == str(contract_id)).one()
    assert order.status == "closed"
    assert order.meta["realized_pnl"] == pytest.approx(float(closed.json()["sold_for"]) - float(order.meta["stake"]))
    position = db.get(Position, order.meta["position_id"])
    assert position.status == "closed"
    assert float(position.realized_pnl) == pytest.approx(order.meta["realized_pnl"])
    assert position.closed_at is not None

    after = client.get(f"{BASE}/deriv/connections/{connection_id}/contracts", headers=trader["headers"])
    assert after.json()["open_contracts"] == 0


def test_session_endpoints_open_and_close(client, trader, deriv_env):
    connection_id = _connect(client, trader).json()["id"]

    opened = client.post(f"{BASE}/deriv/connections/{connection_id}/session/connect", headers=trader["headers"])
    assert opened.status_code == 200, opened.text
    assert opened.json()["session"]["connected"] is True
    assert opened.json()["session"]["trading_paused"] is False

    closed = client.post(f"{BASE}/deriv/connections/{connection_id}/session/close", headers=trader["headers"])
    assert closed.status_code == 200
    assert deriv_sessions.get_session(connection_id) is None


def test_failed_authentication_is_recorded_for_operators(client, trader, deriv_env, db):
    deriv_env.state.reject_token = True
    _connect(client, trader)

    rows = client.get(
        f"{BASE}/deriv/connections/{_any_connection_id(db, trader['org_id'])}/status",
        headers=trader["headers"],
    )
    assert rows.status_code in (200, 404)
    from app.db.models import ProviderAuthEvent

    events = db.query(ProviderAuthEvent).filter(ProviderAuthEvent.org_id == trader["org_id"]).all()
    assert events and events[0].outcome == "failed"
    assert events[0].code == "deriv_invalid_token"
    assert deriv_env.state.token not in (events[0].message or "")


def _any_connection_id(db, org_id: str) -> str:
    row = db.query(Connection).filter(Connection.org_id == org_id).first()
    return row.id if row else "00000000-0000-0000-0000-000000000000"


# ------------------------------------------------------------------ automation
def test_automation_config_round_trip(client, automation_trader, deriv_env):
    connection_id = _connect(client, automation_trader).json()["id"]

    put = client.put(
        f"{BASE}/deriv/connections/{connection_id}/automation",
        json={"enabled": True, "mode": "approval", "symbol": "R_100", "stake": 5},
        headers=automation_trader["headers"],
    )
    assert put.status_code == 200, put.text
    assert put.json()["automation"]["mode"] == "approval"

    get = client.get(f"{BASE}/deriv/connections/{connection_id}/automation", headers=automation_trader["headers"])
    assert get.json()["automation"]["enabled"] is True
    assert get.json()["automation"]["stake"] == 5.0


def test_autonomous_mode_requires_a_passable_gate(client, automation_trader, deriv_env):
    connection_id = _connect(client, automation_trader, environment="read_only").json()["id"]

    response = client.put(
        f"{BASE}/deriv/connections/{connection_id}/automation",
        json={"enabled": True, "mode": "autonomous"},
        headers=automation_trader["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "autonomous_mode_blocked"


def test_pending_signal_is_approved_and_executed(client, trader, deriv_env, db):
    connection_id = _connect(client, trader).json()["id"]
    config = AutoTradeConfig(
        org_id=trader["org_id"],
        connection_id=connection_id,
        enabled=True,
        mode="approval",
        symbol="R_100",
        contract_type="CALL",
        stake=10,
        duration=60,
        duration_unit="s",
        created_by=trader["user_id"],
    )
    db.add(config)
    db.flush()
    signal = AutoTradeSignal(
        org_id=trader["org_id"],
        connection_id=connection_id,
        config_id=config.id,
        status="pending",
        mode="approval",
        symbol="R_100",
        side="buy",
        contract_type="CALL",
        stake=10,
        duration=60,
        duration_unit="s",
        reason="qa signal",
    )
    db.add(signal)
    db.commit()

    approved = client.post(f"{BASE}/deriv/signals/{signal.id}/approve", headers=trader["headers"])
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["approved"] is True, body["risk"]
    assert body["order"]["status"] == "filled"

    db.expire_all()
    refreshed = db.get(AutoTradeSignal, signal.id)
    assert refreshed.status == "executed"
    assert refreshed.order_id == body["order"]["id"]
    assert refreshed.contract_id


def test_signal_rejection_keeps_it_out_of_the_venue(client, trader, deriv_env, db):
    connection_id = _connect(client, trader).json()["id"]
    signal = AutoTradeSignal(
        org_id=trader["org_id"],
        connection_id=connection_id,
        status="pending",
        mode="approval",
        symbol="R_100",
        side="buy",
        contract_type="CALL",
        stake=10,
        duration=60,
        duration_unit="s",
        reason="qa signal",
    )
    db.add(signal)
    db.commit()

    rejected = client.post(f"{BASE}/deriv/signals/{signal.id}/reject", headers=trader["headers"])
    assert rejected.status_code == 200
    db.expire_all()
    assert db.get(AutoTradeSignal, signal.id).status == "rejected"
    assert deriv_env.state.contracts == {}


# ------------------------------------------------------- duration floor and venue menu
def test_preview_offers_only_terms_at_or_above_the_floor(client, trader, deriv_env):
    connection_id = _connect(client, trader).json()["id"]

    response = client.post(
        f"{BASE}/deriv/connections/{connection_id}/preview",
        json={"symbol": "R_100", "side": "buy", "stake": 10, "duration": 60, "duration_unit": "s"},
        headers=trader["headers"],
    )
    assert response.status_code == 200, response.text
    terms = response.json()["terms"]
    assert terms["term"] == "60s"
    assert "60s" in terms["allowed_terms"]
    # The venue prices ticks and 15-second contracts; the platform must not offer them.
    assert "5t" not in terms["allowed_terms"]
    assert "30s" not in terms["allowed_terms"]
    assert all(int(term[:-1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[term[-1]] >= 60
               for term in terms["allowed_terms"])
    assert terms["term_source"] == "venue"


def test_preview_rejects_a_term_the_venue_does_not_offer(client, trader, deriv_env):
    connection_id = _connect(client, trader).json()["id"]

    response = client.post(
        f"{BASE}/deriv/connections/{connection_id}/preview",
        json={"symbol": "R_100", "side": "buy", "stake": 10, "duration": 61, "duration_unit": "s"},
        headers=trader["headers"],
    )
    assert response.status_code == 400, response.text
    body = response.json()["detail"]
    assert body["code"] == "unsupported_duration"
    assert "60s" in body["details"]["allowed"]


def test_sub_minute_terms_are_refused_before_execution(client, trader, deriv_env):
    """The schema refuses a sub-minute term, so it never reaches the venue or the engine."""
    connection_id = _connect(client, trader).json()["id"]
    priced_before = len(deriv_env.state.proposals)

    for duration, unit in ((5, "t"), (30, "s"), (1, "t")):
        response = client.post(
            f"{BASE}/deriv/connections/{connection_id}/preview",
            json={"symbol": "R_100", "side": "buy", "stake": 10, "duration": duration, "duration_unit": unit},
            headers=trader["headers"],
        )
        assert response.status_code == 422, (duration, unit, response.text)
    assert len(deriv_env.state.proposals) == priced_before


def test_execution_layer_refuses_a_sub_minute_term_even_without_the_schema(client, trader, deriv_env):
    """Defence in depth: the floor lives in the execution layer, not only in the request model."""
    from app.core.errors import AppError
    from app.db.models import Connection
    from app.trading import deriv_execution

    connection_id = _connect(client, trader).json()["id"]
    priced_before = len(deriv_env.state.proposals)
    with SessionLocal() as db:
        connection = db.get(Connection, connection_id)
        user = db.get(User, connection.created_by)
        with pytest.raises(AppError) as excinfo:
            deriv_execution.preview(
                db,
                user=user,
                connection=connection,
                payload={"symbol": "R_100", "side": "buy", "stake": 10, "duration": 5, "duration_unit": "t"},
            )
    assert excinfo.value.detail["code"] == "min_duration"
    assert len(deriv_env.state.proposals) == priced_before


def test_automation_config_refuses_a_sub_minute_duration(client, trader, deriv_env):
    connection_id = _connect(client, trader).json()["id"]

    response = client.put(
        f"{BASE}/deriv/connections/{connection_id}/automation",
        json={"enabled": True, "mode": "autonomous", "duration": 15, "duration_unit": "s"},
        headers=trader["headers"],
    )
    assert response.status_code == 422, response.text
