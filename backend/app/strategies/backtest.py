"""Event-driven backtester.

Deliberate design choices:
* Signals are evaluated on closed bars; entries/exits fill at the *next* bar's open,
  so the engine cannot peek at the future.
* Stops and targets are checked against the current bar's high/low (a stop is a
  resting order in reality), and the fill is worsened by slippage and spread.
* Every fee, spread, slippage and funding estimate is deducted. Results are net.
* No parameter optimisation happens here; walk-forward output is out-of-sample
  consistency, not a search for the best curve fit.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.providers.base import Candle
from app.strategies.base import PositionState, Strategy

ENGINE_VERSION = "1.0.0"
TIMEFRAME_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}
BARS_PER_YEAR = {tf: 365 * 24 * 3600 / sec for tf, sec in TIMEFRAME_SECONDS.items()}


@dataclass
class CostModel:
    fee_bps: float = 10.0
    spread_bps: float = 4.0
    slippage_bps: float = 3.0
    funding_bps_per_day: float = 1.0
    max_position_pct: float = 10.0
    starting_equity: float = 25_000.0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class OpenPosition:
    side: str
    quantity: float
    entry_price: float
    entry_index: int
    entry_reason: str
    stop_loss: float | None
    take_profit: float | None
    entry_fee: float
    funding_paid: float = 0.0


@dataclass
class BacktestResult:
    metrics: dict
    equity_curve: list[dict]
    trades: list[dict]
    data_quality: dict = field(default_factory=dict)
    engine_version: str = ENGINE_VERSION


def _round(value: float, digits: int = 8) -> float:
    return float(f"{value:.{digits}f}")


def run_backtest(
    strategy: Strategy,
    candles: list[Candle],
    params: dict,
    *,
    timeframe: str,
    costs: CostModel | None = None,
    data_meta: dict | None = None,
    max_trades_recorded: int = 300,
) -> BacktestResult:
    costs = costs or CostModel()
    params = {**strategy.default_params, **(params or {})}
    warmup = strategy.warmup_bars(params)
    data_meta = data_meta or {}

    if len(candles) <= warmup + 5:
        raise ValueError(f"Not enough candles ({len(candles)}) for a meaningful backtest; need > {warmup + 5}.")

    bar_seconds = TIMEFRAME_SECONDS.get(timeframe, 3600)
    equity = costs.starting_equity
    cash = equity
    peak = equity
    max_dd = 0.0
    position: OpenPosition | None = None
    trades: list[dict] = []
    curve: list[dict] = []
    total_fees = 0.0
    total_funding = 0.0
    gross_profit = 0.0
    gross_loss = 0.0
    bars_in_market = 0
    consecutive_losses = 0
    max_consecutive_losses = 0

    def half_spread(price: float) -> float:
        return price * costs.spread_bps / 20_000

    def slip(price: float, side: str) -> float:
        adverse = costs.slippage_bps / 10_000
        return price * (1 + adverse) if side == "buy" else price * (1 - adverse)

    def close_position(exit_raw: float, index: int, reason: str, exit_side: str) -> None:
        nonlocal cash, equity, position, total_fees, total_funding, gross_profit, gross_loss, consecutive_losses, max_consecutive_losses
        assert position is not None
        exit_price = slip(exit_raw, exit_side) - half_spread(exit_raw) if exit_side == "sell" else slip(exit_raw, exit_side) + half_spread(exit_raw)
        notional = exit_price * position.quantity
        fee = notional * costs.fee_bps / 10_000
        total_fees += fee
        if position.side == "long":
            pnl = (exit_price - position.entry_price) * position.quantity
        else:
            pnl = (position.entry_price - exit_price) * position.quantity
        net = pnl - fee - position.entry_fee - position.funding_paid
        cash += net
        if pnl > 0:
            gross_profit += pnl
        else:
            gross_loss += abs(pnl)
        if net < 0:
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
        else:
            consecutive_losses = 0
        trades.append(
            {
                "entry_index": position.entry_index,
                "exit_index": index,
                "entry_ts": candles[position.entry_index].ts,
                "exit_ts": candles[index].ts,
                "side": position.side,
                "quantity": _round(position.quantity),
                "entry_price": _round(position.entry_price),
                "exit_price": _round(exit_price),
                "gross_pnl": _round(pnl, 4),
                "fees": _round(fee + position.entry_fee, 4),
                "funding": _round(position.funding_paid, 4),
                "net_pnl": _round(net, 4),
                "bars_held": index - position.entry_index,
                "entry_reason": position.entry_reason,
                "exit_reason": reason,
            }
        )
        position = None

    def open_position(side: str, raw_price: float, index: int, signal, equity_now: float) -> None:
        nonlocal position, cash, total_fees
        fill = slip(raw_price, "buy" if side == "long" else "sell")
        fill = fill + half_spread(raw_price) if side == "long" else fill - half_spread(raw_price)
        stop = signal.stop_loss
        risk_pct = float(params.get("risk_per_trade_pct", 1.0)) / 100.0
        risk_amount = equity_now * risk_pct
        if stop and abs(fill - stop) > 0:
            qty = risk_amount / abs(fill - stop)
        else:
            qty = (equity_now * 0.02) / fill
        max_notional = equity_now * costs.max_position_pct / 100.0
        qty = min(qty, max_notional / fill)
        if qty <= 0:
            return
        notional = qty * fill
        fee = notional * costs.fee_bps / 10_000
        total_fees += fee
        cash -= fee
        position = OpenPosition(
            side=side,
            quantity=qty,
            entry_price=fill,
            entry_index=index,
            entry_reason=signal.reason,
            stop_loss=stop,
            take_profit=signal.take_profit,
            entry_fee=fee,
        )

    last_index = len(candles) - 1
    for i in range(warmup, last_index):
        bar = candles[i]
        if position is not None:
            bars_in_market += 1
            position.funding_paid += (
                position.quantity * bar.close * costs.funding_bps_per_day / 10_000 * (bar_seconds / 86_400)
            )
            total_funding = position.funding_paid
            if position.side == "long":
                if position.stop_loss and bar.low <= position.stop_loss:
                    close_position(position.stop_loss, i, "Stop-loss triggered (intrabar).", "sell")
                elif position.take_profit and bar.high >= position.take_profit:
                    close_position(position.take_profit, i, "Take-profit triggered (intrabar).", "sell")
            else:
                if position.stop_loss and bar.high >= position.stop_loss:
                    close_position(position.stop_loss, i, "Stop-loss triggered (intrabar).", "buy")
                elif position.take_profit and bar.low <= position.take_profit:
                    close_position(position.take_profit, i, "Take-profit triggered (intrabar).", "buy")

        history = candles[: i + 1]
        state = (
            PositionState(
                side=position.side,
                quantity=position.quantity,
                entry_price=position.entry_price,
                bars_held=i - position.entry_index,
            )
            if position
            else None
        )
        signal = strategy.generate(history, params, state)
        next_open = candles[i + 1].open

        if position is None and signal.action in ("buy", "sell"):
            open_position("long" if signal.action == "buy" else "short", next_open, i + 1, signal, cash)
        elif position is not None and signal.action == "exit":
            exit_side = "sell" if position.side == "long" else "buy"
            close_position(next_open, i + 1, signal.reason, exit_side)

        mark = bar.close
        unrealised = 0.0
        if position is not None:
            unrealised = (
                (mark - position.entry_price) * position.quantity
                if position.side == "long"
                else (position.entry_price - mark) * position.quantity
            )
        equity = cash + unrealised
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100)
        curve.append({"ts": bar.ts, "equity": _round(equity, 2)})

    # Close any open position at the final close so reported P&L is realised.
    if position is not None:
        exit_side = "sell" if position.side == "long" else "buy"
        close_position(candles[last_index].close, last_index, "Backtest ended; position closed at final close.", exit_side)
        equity = cash
        curve.append({"ts": candles[last_index].ts, "equity": _round(equity, 2)})

    final_equity = equity
    net_profit = final_equity - costs.starting_equity
    total_return_pct = net_profit / costs.starting_equity * 100

    # Bar-level returns for risk-adjusted statistics.
    returns: list[float] = []
    for j in range(1, len(curve)):
        prev = curve[j - 1]["equity"]
        if prev:
            returns.append(curve[j]["equity"] / prev - 1)
    bars_per_year = BARS_PER_YEAR.get(timeframe, 8760)
    mean_ret = sum(returns) / len(returns) if returns else 0.0
    variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1) if len(returns) > 1 else 0.0
    std = math.sqrt(variance)
    downside = [r for r in returns if r < 0]
    downside_var = sum(r * r for r in downside) / len(downside) if downside else 0.0
    sharpe = (mean_ret / std * math.sqrt(bars_per_year)) if std > 0 else 0.0
    sortino = (mean_ret / math.sqrt(downside_var) * math.sqrt(bars_per_year)) if downside_var > 0 else 0.0

    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    gross_win = sum(t["net_pnl"] for t in wins)
    gross_lose = abs(sum(t["net_pnl"] for t in losses))
    duration_days = max(1e-9, (candles[last_index].ts - candles[warmup].ts) / 1000 / 86_400)
    cagr = ((final_equity / costs.starting_equity) ** (365 / duration_days) - 1) * 100 if final_equity > 0 else -100.0
    buy_hold = (candles[last_index].close / candles[warmup].close - 1) * 100

    metrics = {
        "starting_equity": costs.starting_equity,
        "final_equity": _round(final_equity, 2),
        "net_profit": _round(net_profit, 2),
        "total_return_pct": _round(total_return_pct, 4),
        "cagr_pct": _round(cagr, 4),
        "max_drawdown_pct": _round(max_dd, 4),
        "sharpe": _round(sharpe, 3),
        "sortino": _round(sortino, 3),
        "trades": len(trades),
        "win_rate_pct": _round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
        "profit_factor": _round(gross_win / gross_lose, 3) if gross_lose > 0 else (None if not wins else 999.0),
        "expectancy": _round(net_profit / len(trades), 4) if trades else 0.0,
        "avg_win": _round(gross_win / len(wins), 2) if wins else 0.0,
        "avg_loss": _round(-gross_lose / len(losses), 2) if losses else 0.0,
        "total_fees": _round(total_fees, 2),
        "total_funding_est": _round(total_funding, 2),
        "cost_drag_pct": _round((total_fees + total_funding) / costs.starting_equity * 100, 4),
        "gross_profit": _round(gross_profit, 2),
        "gross_loss": _round(gross_loss, 2),
        "avg_bars_held": _round(sum(t["bars_held"] for t in trades) / len(trades), 1) if trades else 0.0,
        "exposure_pct": _round(bars_in_market / max(1, len(curve)) * 100, 2),
        "buy_hold_return_pct": _round(buy_hold, 4),
        "max_consecutive_losses": max_consecutive_losses,
        "duration_days": _round(duration_days, 2),
        "cost_model": costs.as_dict(),
        "timeframe": timeframe,
        "engine_version": ENGINE_VERSION,
    }

    if len(curve) > 400:
        step = max(1, len(curve) // 400)
        sampled = curve[::step]
        if sampled[-1] != curve[-1]:
            sampled.append(curve[-1])
        curve = sampled

    return BacktestResult(
        metrics=metrics,
        equity_curve=curve,
        trades=trades[-max_trades_recorded:],
        data_quality={
            "candles": len(candles),
            "warmup_bars": warmup,
            "source": data_meta.get("source", "unknown"),
            "is_demo": bool(data_meta.get("is_demo", False)),
            "note": data_meta.get("note", ""),
        },
    )


def walk_forward(
    strategy: Strategy,
    candles: list[Candle],
    params: dict,
    *,
    timeframe: str,
    costs: CostModel | None = None,
    folds: int = 4,
    data_meta: dict | None = None,
) -> dict:
    """Sequential out-of-sample folds with fixed parameters (no optimisation)."""
    if len(candles) < 200:
        raise ValueError("Walk-forward needs at least 200 candles.")
    folds = max(2, min(folds, 8))
    size = len(candles) // folds
    results = []
    for k in range(folds):
        start = k * size
        end = len(candles) if k == folds - 1 else (k + 1) * size
        window = candles[start:end]
        if len(window) < 120:
            continue
        try:
            res = run_backtest(strategy, window, params, timeframe=timeframe, costs=costs, data_meta=data_meta)
        except ValueError:
            continue
        results.append(
            {
                "fold": k + 1,
                "start_ts": window[0].ts,
                "end_ts": window[-1].ts,
                "return_pct": res.metrics["total_return_pct"],
                "max_drawdown_pct": res.metrics["max_drawdown_pct"],
                "trades": res.metrics["trades"],
                "sharpe": res.metrics["sharpe"],
            }
        )
    positive = sum(1 for r in results if r["return_pct"] > 0)
    return {
        "folds": results,
        "positive_folds": positive,
        "total_folds": len(results),
        "consistency_pct": round(positive / len(results) * 100, 2) if results else 0.0,
        "methodology": "Fixed parameters replayed on sequential windows. No in-sample optimisation; this measures "
        "stability, not best-case fit.",
        "generated_at": datetime.now(UTC).isoformat(),
    }
