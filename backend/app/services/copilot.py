"""Deterministic market copilot.

This is an explainable technical-analysis engine, not a language model. It reads
the same candles the terminal renders, computes standard indicators and returns a
structured read of the market with the reasoning attached. Nothing here predicts
prices, promises returns or places orders; the output is labelled as analysis and
carries its data provenance so a demo feed can never be mistaken for live data.

The design is deliberate: a small, auditable model that always produces the same
answer for the same candles beats an opaque text generator on a trading platform.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.services import market_data
from app.strategies import indicators

MODEL_NAME = "veltrane-technical-v1"


@dataclass
class Read:
    bias: str
    confidence: int
    rationale: list[str]
    invalidation: str


def _last(values: list[float | None]) -> float | None:
    for value in reversed(values):
        if value is not None:
            return float(value)
    return None


def analyse(symbol: str, timeframe: str = "15m", duration_seconds: int | None = None) -> dict:
    candles, meta = market_data.get_candles(symbol, timeframe=timeframe, limit=200)
    if len(candles) < 60:
        raise ValueError("Not enough candles to analyse this instrument.")

    closes = [c.close for c in candles]
    price = closes[-1]
    ema_fast = _last(indicators.ema(closes, 12))
    ema_slow = _last(indicators.ema(closes, 48))
    rsi_value = _last(indicators.rsi(closes, 14))
    atr_value = _last(indicators.atr(candles, 14))
    upper, lower = indicators.donchian(candles, 20)
    range_high, range_low = _last(upper), _last(lower)

    atr_pct = (atr_value / price * 100) if atr_value and price else 0.0
    trend = "up" if ema_fast and ema_slow and ema_fast > ema_slow else "down"
    momentum = "strong" if rsi_value and rsi_value > 62 else ("weak" if rsi_value and rsi_value < 38 else "balanced")

    score = 0
    rationale: list[str] = []
    if ema_fast and ema_slow:
        gap = (ema_fast - ema_slow) / ema_slow * 100
        score += 2 if gap > 0.15 else (-2 if gap < -0.15 else 0)
        rationale.append(
            f"EMA12 is {gap:+.2f}% versus EMA48, so the short-term trend is {trend}."
        )
    if rsi_value is not None:
        if rsi_value > 70:
            score -= 1
            rationale.append(f"RSI {rsi_value:.1f} is overbought, which argues for a pullback rather than a chase.")
        elif rsi_value < 30:
            score += 1
            rationale.append(f"RSI {rsi_value:.1f} is oversold, which argues for a bounce rather than a breakdown.")
        else:
            rationale.append(f"RSI {rsi_value:.1f} is mid-range: momentum is {momentum}.")
    if range_high and range_low and range_high > range_low:
        position = (price - range_low) / (range_high - range_low)
        rationale.append(
            f"Price sits at {position * 100:.0f}% of the 20-bar Donchian range ({range_low:.4g}-{range_high:.4g})."
        )
        if position > 0.85:
            score -= 1
            rationale.append("Near the top of the range, so a long here pays worse odds than a fade.")
        elif position < 0.15:
            score += 1
            rationale.append("Near the bottom of the range, so a short here pays worse odds than a bounce.")

    if duration_seconds is not None and duration_seconds <= 300:
        score = int(round(score * 0.5))
        rationale.append(
            f"A {duration_seconds}s expiry is noise-dominated; the signal weight is halved on purpose."
        )

    if atr_pct > 1.2:
        rationale.append(
            f"14-bar ATR is {atr_pct:.2f}% of price, so short expiries can be stopped out by normal noise."
        )

    bias = "call" if score >= 2 else ("put" if score <= -2 else "neutral")
    confidence = min(85, 40 + abs(score) * 10)
    invalidation = (
        f"A close back below {ema_slow:.4g} would invalidate the long read."
        if bias == "call" and ema_slow
        else f"A close back above {ema_slow:.4g} would invalidate the short read."
        if bias == "put" and ema_slow
        else "No directional edge is established; treat any contract as a coin flip with costs."
    )

    return {
        "model": MODEL_NAME,
        "symbol": symbol,
        "timeframe": timeframe,
        "generated_at": datetime.now(UTC).isoformat(),
        "price": price,
        "bias": bias,
        "confidence": confidence,
        "trend": trend,
        "momentum": momentum,
        "rsi": round(rsi_value, 2) if rsi_value is not None else None,
        "atr_pct": round(atr_pct, 3),
        "range": {"low": range_low, "high": range_high},
        "rationale": rationale,
        "invalidation": invalidation,
        "data": {
            "source": meta.get("source"),
            "is_demo": meta.get("is_demo", True),
            "candles": len(candles),
        },
        "disclaimer": (
            "Deterministic technical analysis on the data shown, not advice and not a prediction. "
            "Most short-dated contracts lose money after costs. Never risk funds you cannot afford to lose."
        ),
    }


def briefing(limit: int = 6) -> dict:
    """A compact, honest read across the tradable universe for the dashboard."""
    rows = []
    for asset in market_data.supported_symbols():
        if asset["asset_class"] == "index":
            continue
        try:
            read = analyse(asset["symbol"], timeframe="15m")
        except Exception:  # a single unreadable symbol must not blank the whole briefing
            continue
        rows.append(
            {
                "symbol": asset["symbol"],
                "asset_class": asset["asset_class"],
                "price": read["price"],
                "bias": read["bias"],
                "confidence": read["confidence"],
                "trend": read["trend"],
                "rsi": read["rsi"],
                "is_demo": read["data"]["is_demo"],
            }
        )
        if len(rows) >= limit:
            break
    return {
        "model": MODEL_NAME,
        "generated_at": datetime.now(UTC).isoformat(),
        "rows": rows,
        "disclaimer": (
            "Deterministic technical reads on simulated or provider data. Not advice, not a signal service, "
            "and not a guarantee of any outcome."
        ),
    }
