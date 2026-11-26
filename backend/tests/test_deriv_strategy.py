"""Unit tests for the baseline Deriv entry trigger and the automation guards."""

from __future__ import annotations

from app.providers.base import Candle
from app.trading.deriv_strategy import ema, evaluate_entry, rsi


def _candles(closes: list[float]) -> list[Candle]:
    return [Candle(ts=1_700_000_000 + i * 60, open=c, high=c, low=c, close=c, volume=0.0) for i, c in enumerate(closes)]


def test_ema_converges_on_a_constant_series():
    series = ema([5.0] * 30, 9)
    assert all(abs(value - 5.0) < 1e-9 for value in series)


def test_rsi_is_high_on_an_unbroken_advance():
    closes = [100 + i for i in range(40)]
    assert rsi(closes) > 90


def test_rsi_is_low_on_an_unbroken_decline():
    closes = [200 - i for i in range(40)]
    assert rsi(closes) < 10


def test_no_signal_without_enough_history():
    assert evaluate_entry(_candles([100.0] * 10)) is None


def test_no_signal_on_a_flat_series():
    assert evaluate_entry(_candles([100.0] * 60)) is None


def _cross_index(closes: list[float], *, up: bool) -> int:
    """Index of the bar where EMA9 crosses EMA21 in the requested direction."""
    fast = ema(closes, 9)
    slow = ema(closes, 21)
    for i in range(1, len(closes)):
        if up and fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]:
            return i
        if not up and fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]:
            return i
    raise AssertionError("test fixture never crosses")


def _v_shape(*, up: bool) -> list[float]:
    """A trend, a reversal, then a small pullback so RSI stays inside the filter band."""
    sign = -1 if up else 1
    closes = [100 + sign * i * 0.6 for i in range(40)]
    base = closes[-1]
    closes += [base - sign * i * 2.0 for i in range(1, 6)]
    turn = closes[-1]
    closes += [turn + sign * i * 0.3 for i in range(1, 3)]
    return closes


def test_cross_up_produces_a_call():
    # A decline, a reversal and a shallow pullback. The signal appears on the crossing bar.
    closes = _v_shape(up=True)
    index = _cross_index(closes, up=True)
    assert index == len(closes) - 1
    decision = evaluate_entry(_candles(closes))

    assert decision is not None
    assert decision.contract_type == "CALL"
    assert decision.strategy == "ema_cross_rsi_v1"
    assert "no profitability claim" in decision.reason
    assert decision.indicators["ema_fast"] > decision.indicators["ema_slow"]
    assert decision.indicators["rsi"] < 70


def test_cross_down_produces_a_put():
    closes = _v_shape(up=False)
    index = _cross_index(closes, up=False)
    assert index == len(closes) - 1
    decision = evaluate_entry(_candles(closes))

    assert decision is not None
    assert decision.contract_type == "PUT"
    assert decision.indicators["ema_fast"] < decision.indicators["ema_slow"]
    assert decision.indicators["rsi"] > 30


def test_a_signal_is_not_repeated_on_the_bar_after_the_cross():
    closes = _v_shape(up=True)
    assert evaluate_entry(_candles(closes)) is not None
    # The trigger fires on the crossing bar only; the next bar is not a new setup.
    assert evaluate_entry(_candles(closes + [closes[-1] + 0.3])) is None
