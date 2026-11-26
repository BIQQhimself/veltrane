"""Baseline entry trigger for automated Deriv contracts.

Deliberately simple and fully specified so the platform never implies a hidden edge:

* EMA(9) crossing above EMA(21) with RSI(14) below 70 → CALL.
* EMA(9) crossing below EMA(21) with RSI(14) above 30 → PUT.
* Anything else → no trade.

The trigger only proposes a direction. Sizing, exposure, loss limits, kill switches, staleness
and duplicate checks are decided by the deterministic risk engine, never here. Backtest results
for this trigger are recorded in ``INTEGRATIONS.md`` when they are actually produced; none are
claimed in advance.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.providers.base import Candle

STRATEGY = "ema_cross_rsi_v1"


@dataclass(frozen=True)
class EntryDecision:
    contract_type: str  # CALL | PUT
    reason: str
    strategy: str
    indicators: dict


def ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(value * k + out[-1] * (1 - k))
    return out


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        return 50.0
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        change = values[i] - values[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def evaluate_entry(candles: list[Candle], *, fast: int = 9, slow: int = 21) -> EntryDecision | None:
    closes = [c.close for c in candles]
    if len(closes) < slow + 3:
        return None
    fast_series = ema(closes, fast)
    slow_series = ema(closes, slow)
    prev_fast, prev_slow = fast_series[-2], slow_series[-2]
    last_fast, last_slow = fast_series[-1], slow_series[-1]
    momentum = rsi(closes)
    indicators = {
        "ema_fast": round(last_fast, 6),
        "ema_slow": round(last_slow, 6),
        "rsi": round(momentum, 3),
        "close": closes[-1],
        "samples": len(closes),
    }

    crossed_up = prev_fast <= prev_slow and last_fast > last_slow
    crossed_down = prev_fast >= prev_slow and last_fast < last_slow

    if crossed_up and momentum < 70:
        return EntryDecision(
            contract_type="CALL",
            reason=(
                f"EMA{fast} crossed above EMA{slow} with RSI {momentum:.1f} (<70). "
                "Technical trigger only; no profitability claim."
            ),
            strategy=STRATEGY,
            indicators=indicators,
        )
    if crossed_down and momentum > 30:
        return EntryDecision(
            contract_type="PUT",
            reason=(
                f"EMA{fast} crossed below EMA{slow} with RSI {momentum:.1f} (>30). "
                "Technical trigger only; no profitability claim."
            ),
            strategy=STRATEGY,
            indicators=indicators,
        )
    return None
