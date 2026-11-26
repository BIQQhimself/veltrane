"""The scheduled Deriv runner: signal generation, approval mode and autonomous execution.

The venue is the protocol mock, so the candles the strategy sees are the venue's own candles and
the contract that results is a real contract in the mock's ledger. Nothing here reaches the public
internet and no real-money account is touched.
"""

from __future__ import annotations

import math
import time

import pytest
from app.core.config import settings
from app.db.models import AutoTradeConfig, AutoTradeSignal, Order, Trade
from app.services import autotrade, deriv_sessions, kill_switch
from app.trading.deriv_strategy import ema, rsi

BASE = "/api/v1"


def cross_candles() -> list[dict]:
    """A deterministic wave, newest first, whose last bar is an EMA9-above-EMA21 cross with RSI < 70.

    Straight-line series cannot satisfy both conditions: any rally steep enough to cross the EMAs
    also pushes RSI over 70, which the strategy treats as too late to enter. A wave with a small
    pullback inside it can.
    """
    closes = [round(100 + 2 * math.sin(math.radians(170) + 2 * math.pi * i / 14), 2) for i in range(80)]
    now = int(time.time())
    rows = []
    previous = closes[0]
    for index, close in enumerate(closes):
        rows.append(
            {
                "epoch": now - 60 * (len(closes) - index),
                "open": previous,
                "high": max(previous, close) + 0.5,
                "low": min(previous, close) - 0.5,
                "close": close,
            }
        )
        previous = close
    rows.reverse()
    return rows


@pytest.fixture
def deriv_env(mock_deriv, monkeypatch):
    mock_deriv.state.reset()
    monkeypatch.setattr(settings, "deriv_rest_base", mock_deriv.base_url)
    monkeypatch.setattr(settings, "deriv_public_ws_url", mock_deriv.public_ws_url)
    monkeypatch.setattr(settings, "deriv_app_id", mock_deriv.state.app_id)
    deriv_sessions.close_all()
    yield mock_deriv
    mock_deriv.state.reset()
    deriv_sessions.close_all()


def _connect(client, trader, *, account_id="VRTC900001", environment="live"):
    response = client.post(
        f"{BASE}/connections",
        json={
            "provider": "deriv",
            "label": f"Deriv {account_id}",
            "environment": environment,
            "api_key": "pat_test_token_0123456789abcdef",
            "app_id": "12345",
            "account_id": account_id,
        },
        headers=trader["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _config(db, trader, connection_id, mode: str) -> AutoTradeConfig:
    config = AutoTradeConfig(
        org_id=trader["org_id"],
        connection_id=connection_id,
        enabled=True,
        mode=mode,
        symbol="R_100",
        contract_type="CALL",
        stake=10,
        duration=5,
        duration_unit="t",
        max_open_contracts=1,
        max_stake_per_trade=25,
        daily_loss_limit=100,
        daily_stake_limit=250,
        cooldown_seconds=0,
        created_by=trader["user_id"],
    )
    db.add(config)
    db.commit()
    return config


def test_crafted_series_really_contains_the_crossing_the_runner_needs():
    rows = cross_candles()
    closes = [row["close"] for row in reversed(rows)]
    fast, slow = ema(closes, 9), ema(closes, 21)
    assert fast[-2] <= slow[-2]
    assert fast[-1] > slow[-1]
    assert rsi(closes) < 70


def test_runner_creates_a_pending_signal_in_approval_mode(client, trader, deriv_env, db):
    deriv_env.state.candle_override = cross_candles()
    connection_id = _connect(client, trader)
    _config(db, trader, connection_id, "approval")

    summary = autotrade.run_once(db)
    db.commit()

    assert summary["configs"] == 1
    signals = db.query(AutoTradeSignal).filter(AutoTradeSignal.connection_id == connection_id).all()
    assert len(signals) == 1
    signal = signals[0]
    assert signal.status == "pending"
    assert signal.contract_type == "CALL"
    assert signal.side == "buy"
    assert "EMA9 crossed above EMA21" in signal.reason
    assert signal.risk_snapshot["indicators"]["ema_fast"] > signal.risk_snapshot["indicators"]["ema_slow"]
    # Approval mode never sends anything to the venue on its own.
    assert db.query(Order).filter(Order.connection_id == connection_id).count() == 0
    assert deriv_env.state.contracts == {}

    approved = client.post(f"{BASE}/deriv/signals/{signal.id}/approve", headers=trader["headers"])
    assert approved.status_code == 200, approved.text
    assert approved.json()["approved"] is True, approved.json()["risk"]
    assert approved.json()["order"]["status"] == "filled"

    db.expire_all()
    refreshed = db.get(AutoTradeSignal, signal.id)
    assert refreshed.status == "executed"
    assert refreshed.contract_id


def test_runner_executes_autonomously_on_a_demo_account(client, trader, deriv_env, db):
    deriv_env.state.candle_override = cross_candles()
    connection_id = _connect(client, trader)
    _config(db, trader, connection_id, "autonomous")

    summary = autotrade.run_once(db)
    db.commit()

    assert summary["configs"] == 1
    signals = db.query(AutoTradeSignal).filter(AutoTradeSignal.connection_id == connection_id).all()
    assert len(signals) == 1
    signal = signals[0]
    assert signal.status == "executed", (signal.error, summary)
    assert signal.order_id
    assert signal.contract_id
    order = db.get(Order, signal.order_id)
    assert order.status == "filled"
    assert order.is_demo is True
    assert order.meta["account_id"] == "VRTC900001"
    # The demo venue ledger holds the contract: the order was not merely recorded locally.
    assert str(list(deriv_env.state.contracts)[0]) == order.provider_order_id
    assert db.query(Trade).filter(Trade.order_id == order.id).count() == 0  # open, not settled


def test_runner_respects_the_kill_switch(client, trader, deriv_env, db):
    deriv_env.state.candle_override = cross_candles()
    connection_id = _connect(client, trader)
    config = _config(db, trader, connection_id, "autonomous")
    kill_switch.engage(db, scope="provider", target="deriv", actor=None, reason="qa")
    db.commit()

    try:
        summary = autotrade.run_once(db)
        db.commit()
        assert summary["results"][0]["skipped"] == "Kill switch engaged: provider"
        assert db.query(AutoTradeSignal).count() == 0
        assert deriv_env.state.contracts == {}
        db.expire_all()
        assert db.get(AutoTradeConfig, config.id).halt_reason.startswith("Kill switch engaged")
    finally:
        kill_switch.release(db, scope="provider", target="deriv", actor=None)
        db.commit()


def test_runner_without_a_crossing_creates_nothing(client, trader, deriv_env, db):
    connection_id = _connect(client, trader)
    _config(db, trader, connection_id, "approval")

    summary = autotrade.run_once(db)
    db.commit()

    assert summary["results"][0]["reason"] == "no setup"
    assert db.query(AutoTradeSignal).count() == 0


def test_autonomous_signal_rejected_by_the_risk_engine_is_not_reported_as_executed(client, trader, deriv_env, db):
    """The AI may propose; the risk engine decides. A refusal must never read as a filled trade."""
    deriv_env.state.candle_override = cross_candles()
    connection_id = _connect(client, trader)
    # A stake far below the platform minimum notional: the gate passes, the risk engine refuses.
    config = AutoTradeConfig(
        org_id=trader["org_id"],
        connection_id=connection_id,
        enabled=True,
        mode="autonomous",
        symbol="R_100",
        contract_type="CALL",
        stake=0.01,
        duration=5,
        duration_unit="t",
        max_open_contracts=1,
        max_stake_per_trade=25,
        daily_loss_limit=100,
        daily_stake_limit=250,
        cooldown_seconds=0,
        created_by=trader["user_id"],
    )
    db.add(config)
    db.commit()

    summary = autotrade.run_once(db)
    db.commit()

    assert summary["results"][0]["status"] == "rejected"
    signal = db.query(AutoTradeSignal).filter(AutoTradeSignal.connection_id == connection_id).one()
    assert signal.status == "rejected"
    assert signal.contract_id is None
    assert "below the" in signal.error and "minimum" in signal.error
    order = db.get(Order, signal.order_id)
    assert order.status == "rejected"
    assert deriv_env.state.contracts == {}
