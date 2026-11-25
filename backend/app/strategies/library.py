"""System strategy library.

All four strategies are deterministic, fully specified and cost-aware in backtest.
None of them is claimed to be profitable; results depend on market regime and costs.
"""
from __future__ import annotations

from app.providers.base import Candle
from app.strategies.base import PositionState, Signal, Strategy
from app.strategies.indicators import atr, donchian, ema, rate_of_change, rsi, sma


class TrendFollowing(Strategy):
    code = "trend_following_v1"
    name = "Aurum Trend"
    category = "technical"
    summary = "Dual moving-average trend filter with ATR-based stop and trailing exit."
    supported_markets = ["crypto", "forex", "index", "commodity"]
    timeframes = ["1h", "4h", "1d"]
    entry_rules = (
        "Enter long when EMA(fast) crosses above EMA(slow) and price is above the slow EMA. "
        "Enter short (if enabled) on the opposite cross."
    )
    exit_rules = "Exit on the opposite crossover, on the ATR stop, or on the ATR trailing stop."
    data_requirements = "OHLCV candles, at least slow_ema + 20 bars. No funding or order-book data."
    backtest_methodology = (
        "Event-driven bar-by-bar replay with next-bar-open fills, taker fees, spread and slippage applied on "
        "both sides. No parameter optimisation on the test window; walk-forward folds are reported separately."
    )
    known_limitations = (
        "Lags turning points; performs poorly in choppy, range-bound markets; produces many small losses. "
        "Crypto funding costs are estimated, not venue-specific. Slippage model is linear and optimistic in "
        "thin books. Past performance is not indicative of future results."
    )
    params_schema = {
        "fast_ema": {"type": "int", "min": 5, "max": 100, "default": 21},
        "slow_ema": {"type": "int", "min": 20, "max": 400, "default": 80},
        "atr_period": {"type": "int", "min": 5, "max": 50, "default": 14},
        "atr_stop_mult": {"type": "float", "min": 1.0, "max": 6.0, "default": 2.5},
        "risk_per_trade_pct": {"type": "float", "min": 0.1, "max": 3.0, "default": 1.0},
        "allow_short": {"type": "bool", "default": False},
    }
    default_params = {
        "fast_ema": 21,
        "slow_ema": 80,
        "atr_period": 14,
        "atr_stop_mult": 2.5,
        "risk_per_trade_pct": 1.0,
        "allow_short": False,
    }
    risk_params = {"max_position_pct_of_equity": 10.0, "stop_loss_required": True}
    min_bars = 120

    def warmup_bars(self, params: dict) -> int:
        return max(int(params.get("slow_ema", 80)) + 5, 60)

    def generate(self, candles: list[Candle], params: dict, position: PositionState | None) -> Signal:
        p = {**self.default_params, **(params or {})}
        if len(candles) < self.warmup_bars(p) + 2:
            return Signal("hold", "Insufficient history for trend evaluation.")
        closes = [c.close for c in candles]
        fast = ema(closes, int(p["fast_ema"]))
        slow = ema(closes, int(p["slow_ema"]))
        atr_series = atr(candles, int(p["atr_period"]))
        i = len(closes) - 1
        if None in (fast[i], fast[i - 1], slow[i], slow[i - 1], atr_series[i]):
            return Signal("hold", "Indicators not yet defined.")
        price = closes[i]
        crossed_up = fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]
        crossed_down = fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]
        stop_distance = atr_series[i] * float(p["atr_stop_mult"])

        if position is None:
            if crossed_up and price > slow[i]:
                return Signal(
                    "buy",
                    f"EMA{int(p['fast_ema'])} crossed above EMA{int(p['slow_ema'])} with price above the slow EMA.",
                    stop_loss=price - stop_distance,
                    strength=min(1.0, (fast[i] - slow[i]) / (atr_series[i] or 1)),
                    meta={"fast": fast[i], "slow": slow[i], "atr": atr_series[i]},
                )
            if p["allow_short"] and crossed_down and price < slow[i]:
                return Signal(
                    "sell",
                    f"EMA{int(p['fast_ema'])} crossed below EMA{int(p['slow_ema'])} with price below the slow EMA.",
                    stop_loss=price + stop_distance,
                    strength=min(1.0, (slow[i] - fast[i]) / (atr_series[i] or 1)),
                )
            return Signal("hold", "No crossover; trend filter unchanged.")
        if position.side == "long" and crossed_down:
            return Signal("exit", "Opposite EMA crossover closed the long position.")
        if position.side == "short" and crossed_up:
            return Signal("exit", "Opposite EMA crossover closed the short position.")
        return Signal("hold", "Open position remains within trend rules.")


class MeanReversion(Strategy):
    code = "mean_reversion_v1"
    name = "Platinum Reversion"
    category = "technical"
    summary = "RSI oversold reversion with a trend filter and ATR stop."
    supported_markets = ["crypto", "forex", "index", "commodity"]
    timeframes = ["15m", "1h", "4h"]
    entry_rules = "Buy when RSI(period) falls below oversold and price holds above the long-term SMA."
    exit_rules = "Exit when RSI recovers above the exit threshold, or on the ATR stop / take-profit."
    data_requirements = "OHLCV candles; at least 120 bars for the trend filter."
    backtest_methodology = "Bar-by-bar replay, next-bar-open fills, all fees and spread applied per side."
    known_limitations = (
        "Buying weakness fails in sustained downtrends; the trend filter reduces but does not remove that risk. "
        "Sensitive to RSI thresholds; results degrade when spreads widen. Not a guarantee of reversion."
    )
    params_schema = {
        "rsi_period": {"type": "int", "min": 5, "max": 30, "default": 14},
        "oversold": {"type": "float", "min": 10, "max": 40, "default": 30},
        "exit_level": {"type": "float", "min": 45, "max": 80, "default": 55},
        "trend_sma": {"type": "int", "min": 50, "max": 300, "default": 120},
        "atr_stop_mult": {"type": "float", "min": 1.0, "max": 5.0, "default": 2.0},
        "risk_per_trade_pct": {"type": "float", "min": 0.1, "max": 3.0, "default": 1.0},
    }
    default_params = {
        "rsi_period": 14,
        "oversold": 30,
        "exit_level": 55,
        "trend_sma": 120,
        "atr_stop_mult": 2.0,
        "risk_per_trade_pct": 1.0,
    }
    risk_params = {"max_position_pct_of_equity": 10.0, "stop_loss_required": True}
    min_bars = 150

    def generate(self, candles: list[Candle], params: dict, position: PositionState | None) -> Signal:
        p = {**self.default_params, **(params or {})}
        if len(candles) < self.min_bars:
            return Signal("hold", "Insufficient history for mean-reversion evaluation.")
        closes = [c.close for c in candles]
        rsi_series = rsi(closes, int(p["rsi_period"]))
        trend = sma(closes, int(p["trend_sma"]))
        atr_series = atr(candles, 14)
        i = len(closes) - 1
        if rsi_series[i] is None or trend[i] is None or atr_series[i] is None:
            return Signal("hold", "Indicators not yet defined.")
        price = closes[i]
        if position is None:
            if rsi_series[i] <= float(p["oversold"]) and price > trend[i]:
                return Signal(
                    "buy",
                    f"RSI {rsi_series[i]:.1f} is below {p['oversold']} while price holds above SMA{int(p['trend_sma'])}.",
                    stop_loss=price - atr_series[i] * float(p["atr_stop_mult"]),
                    take_profit=price + atr_series[i] * float(p["atr_stop_mult"]) * 2,
                    strength=(float(p["oversold"]) - rsi_series[i]) / 100,
                )
            return Signal("hold", f"RSI {rsi_series[i]:.1f} — no oversold setup.")
        if position.side == "long" and rsi_series[i] >= float(p["exit_level"]):
            return Signal("exit", f"RSI recovered to {rsi_series[i]:.1f}; reversion target met.")
        return Signal("hold", "Open position remains within reversion rules.")


class Breakout(Strategy):
    code = "breakout_v1"
    name = "Obsidian Breakout"
    category = "technical"
    summary = "Donchian channel breakout with volatility-scaled stop and channel exit."
    supported_markets = ["crypto", "forex", "index"]
    timeframes = ["1h", "4h", "1d"]
    entry_rules = "Buy when the close breaks above the prior N-bar high; short the prior N-bar low if shorts are enabled."
    exit_rules = "Exit on the opposite channel touch, the ATR stop, or the time stop."
    data_requirements = "OHLCV candles; N + 20 bars minimum."
    backtest_methodology = "Bar-by-bar replay with next-bar-open fills and full cost model."
    known_limitations = (
        "Breakouts produce frequent false starts in ranging markets; whipsaw losses are normal. "
        "Requires liquidity to avoid slippage on the breakout bar. No claim of edge is made."
    )
    params_schema = {
        "channel": {"type": "int", "min": 10, "max": 100, "default": 20},
        "atr_period": {"type": "int", "min": 5, "max": 50, "default": 14},
        "atr_stop_mult": {"type": "float", "min": 1.0, "max": 5.0, "default": 2.0},
        "max_hold_bars": {"type": "int", "min": 5, "max": 200, "default": 60},
        "allow_short": {"type": "bool", "default": False},
        "risk_per_trade_pct": {"type": "float", "min": 0.1, "max": 3.0, "default": 1.0},
    }
    default_params = {
        "channel": 20,
        "atr_period": 14,
        "atr_stop_mult": 2.0,
        "max_hold_bars": 60,
        "allow_short": False,
        "risk_per_trade_pct": 1.0,
    }
    risk_params = {"max_position_pct_of_equity": 10.0, "stop_loss_required": True}
    min_bars = 60

    def generate(self, candles: list[Candle], params: dict, position: PositionState | None) -> Signal:
        p = {**self.default_params, **(params or {})}
        if len(candles) < int(p["channel"]) + 20:
            return Signal("hold", "Insufficient history for channel evaluation.")
        upper, lower = donchian(candles, int(p["channel"]))
        atr_series = atr(candles, int(p["atr_period"]))
        i = len(candles) - 1
        if upper[i - 1] is None or lower[i - 1] is None or atr_series[i] is None:
            return Signal("hold", "Channel not yet defined.")
        price = candles[i].close
        if position is None:
            if price > upper[i - 1]:
                return Signal(
                    "buy",
                    f"Close {price:.6g} broke above the {int(p['channel'])}-bar high {upper[i - 1]:.6g}.",
                    stop_loss=price - atr_series[i] * float(p["atr_stop_mult"]),
                    strength=min(1.0, (price - upper[i - 1]) / (atr_series[i] or 1)),
                )
            if p["allow_short"] and price < lower[i - 1]:
                return Signal(
                    "sell",
                    f"Close {price:.6g} broke below the {int(p['channel'])}-bar low {lower[i - 1]:.6g}.",
                    stop_loss=price + atr_series[i] * float(p["atr_stop_mult"]),
                )
            return Signal("hold", "Price inside the channel.")
        if position.side == "long" and (price < lower[i] or position.bars_held >= int(p["max_hold_bars"])):
            return Signal("exit", "Long exit: lower channel touched or time stop reached.")
        if position.side == "short" and (price > upper[i] or position.bars_held >= int(p["max_hold_bars"])):
            return Signal("exit", "Short exit: upper channel touched or time stop reached.")
        return Signal("hold", "Open position remains within channel rules.")


class MomentumRotation(Strategy):
    code = "momentum_rotation_v1"
    name = "Champagne Momentum"
    category = "quantitative"
    summary = "Time-series momentum with a volatility filter; intended for portfolio rotation."
    supported_markets = ["crypto", "index"]
    timeframes = ["4h", "1d"]
    entry_rules = "Buy when ROC(period) is above the threshold and realised volatility is below the cap."
    exit_rules = "Exit when ROC turns negative or volatility exceeds the cap."
    data_requirements = "OHLCV candles; 150+ bars for stable volatility estimates."
    backtest_methodology = "Bar-by-bar replay with next-bar-open fills and full cost model."
    known_limitations = (
        "Momentum crashes are real and can be severe. Volatility filters lag regime changes. "
        "This strategy is single-instrument here; cross-sectional rotation is not implemented."
    )
    params_schema = {
        "roc_period": {"type": "int", "min": 5, "max": 120, "default": 30},
        "roc_threshold_pct": {"type": "float", "min": 0.0, "max": 20.0, "default": 2.0},
        "vol_cap_pct": {"type": "float", "min": 1.0, "max": 20.0, "default": 6.0},
        "risk_per_trade_pct": {"type": "float", "min": 0.1, "max": 3.0, "default": 1.0},
    }
    default_params = {"roc_period": 30, "roc_threshold_pct": 2.0, "vol_cap_pct": 6.0, "risk_per_trade_pct": 1.0}
    risk_params = {"max_position_pct_of_equity": 10.0, "stop_loss_required": True}
    min_bars = 150

    def generate(self, candles: list[Candle], params: dict, position: PositionState | None) -> Signal:
        p = {**self.default_params, **(params or {})}
        if len(candles) < self.min_bars:
            return Signal("hold", "Insufficient history for momentum evaluation.")
        closes = [c.close for c in candles]
        roc = rate_of_change(closes, int(p["roc_period"]))
        i = len(closes) - 1
        if roc[i] is None:
            return Signal("hold", "Momentum not yet defined.")
        window = closes[-int(p["roc_period"]) :]
        returns = [(window[j] / window[j - 1] - 1) * 100 for j in range(1, len(window)) if window[j - 1]]
        mean_ret = sum(returns) / len(returns) if returns else 0.0
        variance = sum((r - mean_ret) ** 2 for r in returns) / max(1, len(returns) - 1)
        vol_pct = variance ** 0.5
        if position is None:
            if roc[i] > float(p["roc_threshold_pct"]) and vol_pct < float(p["vol_cap_pct"]):
                return Signal(
                    "buy",
                    f"{int(p['roc_period'])}-bar momentum {roc[i]:.2f}% above threshold with volatility {vol_pct:.2f}%.",
                    stop_loss=closes[i] * 0.95,
                    strength=min(1.0, roc[i] / 20),
                )
            return Signal("hold", f"Momentum {roc[i]:.2f}% / vol {vol_pct:.2f}% — no qualified setup.")
        if position.side == "long" and (roc[i] <= 0 or vol_pct >= float(p["vol_cap_pct"])):
            return Signal("exit", f"Momentum {roc[i]:.2f}% or volatility {vol_pct:.2f}% invalidated the setup.")
        return Signal("hold", "Open position remains within momentum rules.")


LIBRARY: dict[str, Strategy] = {
    s.code: s for s in (TrendFollowing(), MeanReversion(), Breakout(), MomentumRotation())
}


def get_strategy(code: str) -> Strategy | None:
    return LIBRARY.get(code)
