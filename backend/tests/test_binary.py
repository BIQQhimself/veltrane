from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.db.models import BinaryContract
from tests.conftest import BASE


def open_contract(client, headers, **overrides):
    payload = {
        "symbol": "BTC/USDT",
        "direction": "call",
        "stake": 100.0,
        "duration_seconds": 60,
        "reason": "Test contract",
    }
    payload.update(overrides)
    response = client.post(f"{BASE}/binary/contracts", json=payload, headers=headers)
    return response


def test_assets_exclude_indices_and_are_labelled_demo(client, trader):
    body = client.get(f"{BASE}/binary/assets", headers=trader["headers"]).json()
    classes = {a["asset_class"] for a in body["assets"]}
    assert classes == {"crypto", "forex", "stock", "commodity"}
    assert "US30" not in {a["symbol"] for a in body["assets"]}
    assert body["mode"] == "paper"
    assert all(a["is_demo"] for a in body["assets"])
    assert all(1 <= float(a["payouts"]["60"]) <= 95 for a in body["assets"])


def test_quote_returns_payout_and_expiry(client, trader):
    response = client.post(
        f"{BASE}/binary/quote",
        json={"symbol": "EUR/USD", "duration_seconds": 300},
        headers=trader["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["payout_pct"] == 74.0
    assert body["is_demo"] is True
    assert body["price_source"] == "demo"
    assert "not a guarantee" in body["disclaimer"]


def test_open_contract_locks_stake_and_is_audited(client, trader, db):
    # The paper session is created lazily on the first contract, so open one first.
    assert open_contract(client, trader["headers"], stake=50.0).json()["approved"] is True
    before = client.get(f"{BASE}/portfolio/overview", headers=trader["headers"]).json()

    result = open_contract(client, trader["headers"], idempotency_key="bin-test-1")
    assert result.status_code == 201, result.text
    body = result.json()
    assert body["approved"] is True, body["risk_decision"]["failed_rules"]
    assert body["contract"]["status"] == "open"
    assert body["contract"]["is_demo"] is True
    assert body["contract"]["seconds_remaining"] > 0
    assert body["risk_decision"]["decision"] == "approved"
    assert any(c["code"] == "binary_terms" for c in body["risk_decision"]["checks"])

    # The stake is collateral: cash drops, equity is unchanged while the contract is open.
    summary = client.get(f"{BASE}/binary/summary", headers=trader["headers"]).json()
    assert summary["open_stake"] == 150.0
    after = client.get(f"{BASE}/portfolio/overview", headers=trader["headers"]).json()
    assert after["equity"]["simulated_balance_usd"] == before["equity"]["simulated_balance_usd"]

    notes = client.get(f"{BASE}/notifications", headers=trader["headers"]).json()["notifications"]
    assert any("contract open" in n["title"].lower() for n in notes)


def test_contract_rejected_when_stake_exceeds_equity_share(client, trader):
    body = open_contract(client, trader["headers"], stake=5000.0).json()
    assert body["approved"] is False
    assert body["contract"]["status"] == "rejected"
    codes = {r["code"] for r in body["risk_decision"]["failed_rules"]}
    assert "position_size" in codes


def test_contract_rejected_for_unknown_duration(client, trader):
    # 90 seconds clears the one-minute floor but is not an offered term.
    response = open_contract(client, trader["headers"], duration_seconds=90)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_duration"


def test_contract_below_the_one_minute_floor_is_refused_by_the_schema(client, trader):
    response = open_contract(client, trader["headers"], duration_seconds=42)
    assert response.status_code == 422


def test_contract_rejected_for_index_symbol(client, trader):
    response = open_contract(client, trader["headers"], symbol="US30")
    assert response.status_code == 404


def test_idempotent_contract_submission(client, trader):
    first = open_contract(client, trader["headers"], idempotency_key="bin-dup").json()
    second = open_contract(client, trader["headers"], idempotency_key="bin-dup").json()
    assert second["idempotent_replay"] is True
    assert second["contract"]["id"] == first["contract"]["id"]


def test_demo_execution_limit_applies_to_contracts(client, trader):
    for i in range(5):
        body = open_contract(client, trader["headers"], stake=10.0, duration_seconds=60).json()
        assert body["approved"] is True, (i, body)
    sixth = open_contract(client, trader["headers"], stake=10.0, duration_seconds=60).json()
    assert sixth["approved"] is False
    codes = {r["code"] for r in sixth["risk_decision"]["failed_rules"]}
    assert "demo_execution_limit" in codes


def test_settlement_marks_contract_and_writes_trade(client, trader, db):
    body = open_contract(client, trader["headers"], stake=100.0, duration_seconds=60).json()
    contract_id = body["contract"]["id"]

    # Force expiry rather than waiting a minute.
    row = db.get(BinaryContract, contract_id)
    row.expires_at = datetime.now(UTC) - timedelta(seconds=5)
    db.commit()

    settled = client.post(f"{BASE}/binary/settle", headers=trader["headers"]).json()
    assert settled["count"] == 1
    assert settled["settled"][0]["status"] in ("won", "lost", "void")

    trades = client.get(f"{BASE}/trades", headers=trader["headers"]).json()["trades"]
    binary_trades = [t for t in trades if t["risk_snapshot"].get("instrument_type") == "binary"]
    assert binary_trades, trades
    assert binary_trades[0]["is_demo"] is True

    summary = client.get(f"{BASE}/binary/summary", headers=trader["headers"]).json()
    assert summary["settled"] == 1
    assert summary["open"] == 0
    assert summary["is_demo"] is True

    # The clickable trade record must carry the decision that let it through.
    detail = client.get(f"{BASE}/trades/{binary_trades[0]['id']}", headers=trader["headers"]).json()["trade"]
    decision = detail["risk_decision"]
    assert decision is not None, detail
    assert decision["decision"] == "approved"
    assert decision["checks"]
    assert all(check["code"] for check in decision["checks"])


def test_contracts_are_tenant_isolated(client, trader, trader2):
    body = open_contract(client, trader["headers"]).json()
    assert body["approved"] is True, body["risk_decision"]["failed_rules"]
    other = client.get(f"{BASE}/binary/contracts", headers=trader2["headers"]).json()
    assert other["contracts"] == []


def test_copilot_analysis_is_explicitly_not_advice(client, trader):
    response = client.post(
        f"{BASE}/copilot/analyse",
        json={"symbol": "BTC/USDT", "timeframe": "15m", "duration_seconds": 60},
        headers=trader["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model"] == "veltrane-technical-v1"
    assert body["bias"] in ("call", "put", "neutral")
    assert 0 <= body["confidence"] <= 85
    assert body["rationale"]
    assert "not advice" in body["disclaimer"].lower()
    assert body["data"]["is_demo"] is True


def test_copilot_briefing_covers_tradable_assets(client, trader):
    body = client.get(f"{BASE}/copilot/briefing", headers=trader["headers"]).json()
    assert body["rows"]
    assert all(row["symbol"] != "US30" for row in body["rows"])
    assert "not a guarantee" in body["disclaimer"]


def test_late_settlement_uses_the_price_at_expiry(client, trader, db):
    """A worker that runs late must not reprice the contract at 'now'.

    The contract is expired ten minutes ago; settlement has to use the close of the
    bar containing the expiry, so two settlements of the same contract agree.
    """
    from app.services import market_data

    body = open_contract(client, trader["headers"], stake=100.0, duration_seconds=300).json()
    contract_id = body["contract"]["id"]

    expiry = datetime.now(UTC) - timedelta(minutes=10)
    row = db.get(BinaryContract, contract_id)
    row.expires_at = expiry
    db.commit()

    expected = market_data.price_at(row.instrument_symbol, expiry)
    assert expected is not None

    settled = client.post(f"{BASE}/binary/settle", headers=trader["headers"]).json()
    assert settled["count"] == 1
    db.expire_all()
    row = db.get(BinaryContract, contract_id)
    assert float(row.exit_price) == pytest.approx(expected)


def test_missing_expiry_price_voids_the_contract_instead_of_repricing_at_now(
    client, trader, db, monkeypatch
):
    """No authoritative price means no result.

    Substituting the live ticker would silently invent a settlement, so the contract is
    voided, the stake is returned and no Trade row claims a profit or a loss.
    """
    from app.db.models import Trade
    from app.services import market_data

    body = open_contract(client, trader["headers"], stake=100.0, duration_seconds=60).json()
    contract_id = body["contract"]["id"]
    row = db.get(BinaryContract, contract_id)
    row.expires_at = datetime.now(UTC) - timedelta(minutes=5)
    db.commit()
    stake_before = float(row.stake)

    monkeypatch.setattr(market_data, "price_at", lambda *args, **kwargs: None)
    settled = client.post(f"{BASE}/binary/settle", headers=trader["headers"]).json()
    assert settled["count"] == 1

    db.expire_all()
    row = db.get(BinaryContract, contract_id)
    assert row.status == "void"
    assert row.exit_price is None
    assert float(row.net_pnl) == 0.0
    assert row.trade_id is None
    assert db.query(Trade).filter(Trade.paper_session_id == row.paper_session_id).count() == 0

    audit_rows = client.get(f"{BASE}/notifications", headers=trader["headers"]).json()
    titles = [item["title"] for item in audit_rows["notifications"]]
    assert any("settled" in title.lower() for title in titles)
    assert stake_before > 0
