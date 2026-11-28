"""Rank every eligible venue symbol on one comparable scale.

The scanner answers a single question: of everything the connected account may trade right
now, which symbol offers the cleanest setup, in which direction, and how much better is it
than the next one. That lets the automation runner stop being pinned to one hand-picked
symbol and instead deploy its permitted capacity where the evidence is strongest.

What the score is: a ranking heuristic in ``0..100`` built from observable candle features
(trend separation, momentum, persistence, volatility fit, setup freshness). It orders
candidates against each other. It is **not** a win probability, an expected return, or a
profit forecast, and nothing in the product may present it as one.

What the score is not: a filter for the risk engine. Every selected opportunity still becomes
an ``AutoTradeSignal`` and passes the execution gate, the deterministic risk engine and the
venue's own proposal check before money moves.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.providers.base import Candle, ProviderError
from app.trading.deriv_strategy import ema, rsi

log = logging.getLogger(__name__)

MIN_CANDLES = 60
DEFAULT_LOOKBACK = 120
TIMEFRAME = "1m"

# Below this the setup is not worth a slot. Raising activity is never a reason to lower it.
MIN_SCORE = 55.0
# Correlated indices move together, so four synthetic indices at once is one position
# wearing four names. The default cap keeps a scan from concentrating by accident.
DEFAULT_SECTOR_CAP = 2
# A signal that fired in the last few bars is still the same signal.
FRESH_BARS = 6
STALE_BARS = 30

WEIGHTS = {
    "trend": 0.40,
    "momentum": 0.25,
    "persistence": 0.15,
    "volatility": 0.10,
    "freshness": 0.10,
}


@dataclass(frozen=True)
class Opportunity:
    symbol: str
    sector: str
    contract_type: str  # CALL | PUT
    score: float
    reason: str
    indicators: dict[str, Any] = field(default_factory=dict)
    strategy: str = "trend_momentum_v2"

    @property
    def side(self) -> str:
        return "buy" if self.contract_type == "CALL" else "sell"

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "sector": self.sector,
            "contract_type": self.contract_type,
            "side": self.side,
            "score": round(self.score, 1),
            "strategy": self.strategy,
            "reason": self.reason,
            "indicators": self.indicators,
        }


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def atr(candles: Sequence[Candle], period: int = 14) -> float:
    """Average true range over the last ``period`` bars. Zero on a flat series."""
    if len(candles) < 2:
        return 0.0
    window = candles[-period - 1 :]
    ranges = []
    for previous, current in zip(window, window[1:], strict=False):
        ranges.append(
            max(current.high - current.low, abs(current.high - previous.close), abs(current.low - previous.close))
        )
    return sum(ranges) / len(ranges) if ranges else 0.0


def _bars_since_cross(fast: list[float], slow: list[float], limit: int = STALE_BARS) -> int | None:
    """Bars since EMA(fast) last changed side of EMA(slow), or ``None`` beyond ``limit``."""
    upper = min(len(fast), len(slow))
    for offset in range(1, min(limit, upper - 1) + 1):
        i = -offset
        j = -offset - 1
        now_up = fast[i] > slow[i]
        was_up = fast[j] > slow[j]
        if now_up != was_up:
            return offset - 1
    return None


def _trend_component(closes: Sequence[float], atr_value: float, direction: str) -> tuple[float, float]:
    fast = ema(list(closes), 9)[-1]
    slow = ema(list(closes), 21)[-1]
    separation = (fast - slow) / atr_value if atr_value > 0 else 0.0
    aligned = separation if direction == "CALL" else -separation
    # 1.5 ATR of separation is a strong, unambiguous trend on a one-minute series.
    return _clamp(aligned / 1.5), separation


def _momentum_component(momentum: float, direction: str) -> float:
    """Full credit while momentum supports the direction, fading as it becomes exhausted.

    RSI above 70 on a call is not automatically wrong — strong trends stay overbought — but
    the closer it runs to 100 the worse the entry, so the credit decays rather than flipping
    to zero. The same applies mirrored for puts.
    """
    strength = momentum if direction == "CALL" else 100 - momentum
    if strength <= 50:
        return 0.0
    if strength <= 75:
        return 1.0
    return _clamp(1 - (strength - 75) / 40, 0.15, 1.0)


def _persistence_component(closes: Sequence[float], direction: str, window: int = 20) -> float:
    # Measured against the trend line as it stood at the start of the window: comparing to
    # "now" would call every healthy uptrend a coin flip, because the EMA always trails.
    series = ema(list(closes), 21)
    reference = series[max(0, len(series) - window - 1)]
    recent = list(closes)[-window:]
    if not recent:
        return 0.0
    if direction == "CALL":
        share = sum(1 for close in recent if close > reference) / len(recent)
    else:
        share = sum(1 for close in recent if close < reference) / len(recent)
    # 0.4 is a coin flip once trend and momentum are already counted; above it is persistence.
    return _clamp((share - 0.4) / 0.6)


def _volatility_component(atr_value: float, price: float) -> float:
    if price <= 0 or atr_value <= 0:
        return 0.0
    ratio = atr_value / price
    if ratio < 0.0002:
        return 0.2  # too quiet: the payout rarely covers the move
    if ratio > 0.02:
        return 0.2  # too violent: slippage and gap risk dominate
    # Peak credit around 0.15% per bar, falling off toward either extreme.
    distance = abs(ratio - 0.0015) / 0.006
    return _clamp(1 - distance)


def _freshness_component(bars: int | None) -> float:
    if bars is None:
        return 0.3
    if bars <= FRESH_BARS:
        return 1.0
    return _clamp(1 - (bars - FRESH_BARS) / (STALE_BARS - FRESH_BARS))


def score_direction(candles: Sequence[Candle], direction: str) -> tuple[float, dict[str, Any]] | None:
    """Score one direction in isolation. ``None`` when the series is too short."""
    if len(candles) < MIN_CANDLES:
        return None
    closes = [c.close for c in candles]
    atr_value = atr(candles)
    momentum = rsi(closes)
    trend, separation = _trend_component(closes, atr_value, direction)
    bars = _bars_since_cross(ema(closes, 9), ema(closes, 21))
    parts = {
        "trend": trend,
        "momentum": _momentum_component(momentum, direction),
        "persistence": _persistence_component(closes, direction),
        "volatility": _volatility_component(atr_value, closes[-1]),
        "freshness": _freshness_component(bars),
    }
    score = sum(parts[key] * weight for key, weight in WEIGHTS.items()) * 100
    indicators = {
        "rsi": round(momentum, 2),
        "ema_separation_atr": round(separation, 3),
        "atr_pct": round(atr_value / closes[-1] * 100, 3) if closes[-1] else 0.0,
        "bars_since_cross": bars,
        "components": {key: round(value, 3) for key, value in parts.items()},
        "close": closes[-1],
    }
    return round(score, 1), indicators


def evaluate(candles: Sequence[Candle], *, symbol: str = "", sector: str = "unknown") -> Opportunity | None:
    """Best direction for one symbol, or ``None`` when neither side clears the floor.

    Up and Down are scored independently and the stronger side wins; a symbol that is
    strong in both directions (rare, and usually a volatility artefact) is not traded at all.
    """
    call = score_direction(candles, "CALL")
    put = score_direction(candles, "PUT")
    if call is None or put is None:
        return None
    call_score, call_parts = call
    put_score, put_parts = put
    if call_score >= put_score:
        direction, score, parts = "CALL", call_score, call_parts
    else:
        direction, score, parts = "PUT", put_score, put_parts
    if score < MIN_SCORE:
        return None
    return Opportunity(
        symbol=symbol,
        sector=sector,
        contract_type=direction,
        score=score,
        reason=(
            f"{direction} setup scoring {score:.0f}/100: RSI {parts['rsi']:.1f}, "
            f"EMA separation {parts['ema_separation_atr']:+.2f} ATR, "
            f"cross {parts['bars_since_cross'] if parts['bars_since_cross'] is not None else '>30'} bars ago. "
            "Ranking heuristic only; no profitability claim."
        ),
        indicators=parts,
    )


def tradable_universe(adapter: Any) -> list[dict[str, Any]]:
    """Symbols the venue says are open, with their sector. Raises ``ProviderError``."""
    rows = adapter.active_symbols()
    universe = []
    for row in rows:
        if not row.get("underlying_symbol"):
            continue
        if not int(row.get("exchange_is_open") or 0):
            continue
        if int(row.get("is_trading_suspended") or 0):
            continue
        universe.append(
            {
                "symbol": row["underlying_symbol"],
                "name": row.get("underlying_symbol_name") or row["underlying_symbol"],
                "sector": row.get("market") or "unknown",
            }
        )
    return universe


def scan(
    adapter: Any,
    *,
    symbols: Iterable[str] | None = None,
    lookback: int = DEFAULT_LOOKBACK,
    timeframe: str = TIMEFRAME,
) -> tuple[list[Opportunity], dict[str, Any]]:
    """Score every symbol in the universe. One failing symbol never stops the scan."""
    try:
        universe = tradable_universe(adapter)
    except ProviderError as exc:
        return [], {"error": f"universe unavailable: {exc.message}", "scanned": 0, "skipped": 0}
    wanted = set(symbols) if symbols else None
    rows = [row for row in universe if wanted is None or row["symbol"] in wanted]
    found: list[Opportunity] = []
    skipped = 0
    for row in rows:
        try:
            candles = adapter.fetch_ohlcv(row["symbol"], timeframe, lookback)
        except Exception as exc:  # noqa: BLE001 - a venue hiccup must not stop the scan
            log.debug("scan_symbol_failed", extra={"extra_fields": {"symbol": row["symbol"], "error": str(exc)[:120]}})
            skipped += 1
            continue
        opportunity = evaluate(candles, symbol=row["symbol"], sector=row["sector"])
        if opportunity is None:
            continue
        found.append(
            Opportunity(
                symbol=opportunity.symbol,
                sector=opportunity.sector,
                contract_type=opportunity.contract_type,
                score=opportunity.score,
                reason=opportunity.reason,
                indicators={**opportunity.indicators, "name": row["name"]},
            )
        )
    found.sort(key=lambda item: item.score, reverse=True)
    return found, {"scanned": len(rows), "skipped": skipped, "universe": len(universe)}


def select(
    opportunities: Sequence[Opportunity],
    *,
    slots: int,
    sector_cap: int = DEFAULT_SECTOR_CAP,
    exclude_symbols: Iterable[str] = (),
) -> list[Opportunity]:
    """Greedy pick of the strongest candidates that respect the caps.

    ``exclude_symbols`` covers symbols already held or already signalled: the same setup
    twice is one position, not two, and re-entering it is how a bot doubles a loser.
    """
    if slots <= 0:
        return []
    blocked = {symbol for symbol in exclude_symbols}
    per_sector: dict[str, int] = {}
    picked: list[Opportunity] = []
    for opportunity in opportunities:
        if len(picked) >= slots:
            break
        if opportunity.symbol in blocked:
            continue
        if per_sector.get(opportunity.sector, 0) >= sector_cap:
            continue
        per_sector[opportunity.sector] = per_sector.get(opportunity.sector, 0) + 1
        blocked.add(opportunity.symbol)
        picked.append(opportunity)
    return picked


def preview(adapter: Any, *, limit: int = 10, sector_cap: int = DEFAULT_SECTOR_CAP) -> dict[str, Any]:
    """Read-only view for the terminal: the ranked list, nothing executed."""
    found, stats = scan(adapter)
    ranked = select(found, slots=limit, sector_cap=max(limit, sector_cap))
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "sector_cap": sector_cap,
        "qualifying": len(found),
        "opportunities": [item.as_dict() for item in ranked],
        **stats,
    }
