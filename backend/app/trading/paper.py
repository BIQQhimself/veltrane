"""Paper execution engine.

Fills are simulated with a transparent, configurable cost model:
* half-spread crossed on entry and exit,
* adverse slippage in basis points,
* taker fee in basis points on both sides,
* optional per-day funding estimate while a position is held.

The engine is deterministic given (market price, cost model, order) so results are
reproducible. Every fill writes a trade/position/order/fee/ledger/audit trail.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import settings
from app.db.constants import FeeKind, NotificationCategory, OrderStatus, Severity
from app.db.models import Fee, LedgerTransaction, Order, PaperSession, Position, Trade
from app.services import notifications
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


@dataclass
class FillResult:
    filled_qty: float
    price: float
    fee: float
    slippage_actual_bps: float
    realized_pnl: float = 0.0
    closed_trade: Trade | None = None
    position: Position | None = None
    opened: bool = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _mark_price(db: Session, session_id: str, symbol: str, fallback: float) -> float:
    pos = (
        db.query(Position)
        .filter(
            Position.paper_session_id == session_id,
            Position.instrument_symbol == symbol,
            Position.status == "open",
        )
        .first()
    )
    return float(pos.mark_price) if pos and pos.mark_price else fallback


def execute_market_order(
    db: Session,
    *,
    order: Order,
    session: PaperSession,
    reference_price: float,
    side: str,
    quantity: float,
    stop_loss: float | None,
    take_profit: float | None,
    entry_reason: str,
    risk_snapshot: dict,
) -> FillResult:
    fee_bps = settings.paper_taker_fee_bps
    spread_bps = settings.paper_spread_bps
    slippage_bps = settings.paper_slippage_bps

    half_spread = reference_price * spread_bps / 20_000
    adverse = reference_price * slippage_bps / 10_000
    fill_price = reference_price + half_spread + adverse if side == "buy" else reference_price - half_spread - adverse
    slippage_actual_bps = abs(fill_price - reference_price) / reference_price * 10_000 if reference_price else 0.0
    notional = fill_price * quantity
    fee = notional * fee_bps / 10_000
    now = _utcnow()

    position = (
        db.query(Position)
        .filter(
            Position.paper_session_id == session.id,
            Position.instrument_symbol == order.instrument_symbol,
            Position.status == "open",
        )
        .first()
    )

    closed_trade: Trade | None = None
    realized = 0.0
    opened = False

    if position is not None and ((position.side == "long" and side == "sell") or (position.side == "short" and side == "buy")):
        # Reduce or close the existing position.
        close_qty = min(quantity, float(position.quantity))
        gross = (
            (fill_price - float(position.avg_entry_price)) * close_qty
            if position.side == "long"
            else (float(position.avg_entry_price) - fill_price) * close_qty
        )
        exit_fee = fill_price * close_qty * fee_bps / 10_000
        entry_fee_share = 0.0  # entry fee was charged at open and reflected in cash
        net = gross - exit_fee - entry_fee_share
        realized = net
        session.cash_balance = float(session.cash_balance) + net
        position.quantity = float(position.quantity) - close_qty
        position.realized_pnl = float(position.realized_pnl) + net
        if float(position.quantity) <= 1e-12:
            position.status = "closed"
            position.closed_at = now
        closed_trade = Trade(
            org_id=order.org_id,
            order_id=order.id,
            position_id=position.id,
            paper_session_id=session.id,
            mode="paper",
            instrument_symbol=order.instrument_symbol,
            side=position.side,
            quantity=close_qty,
            entry_price=float(position.avg_entry_price),
            exit_price=fill_price,
            notional=fill_price * close_qty,
            fees=exit_fee,
            funding=0.0,
            slippage_est_bps=slippage_bps + spread_bps / 2,
            slippage_actual_bps=slippage_actual_bps,
            gross_pnl=gross,
            net_pnl=net,
            entry_reason=entry_reason,
            exit_reason="Simulated exit order",
            strategy_version_id=order.strategy_version_id,
            risk_snapshot=risk_snapshot,
            is_demo=True,
            opened_at=position.opened_at,
            closed_at=now,
        )
        db.add(closed_trade)
        db.flush()
    else:
        # Open or add to a position (netting engine, long or short).
        new_side = "long" if side == "buy" else "short"
        if position is not None and position.side == new_side:
            total_qty = float(position.quantity) + quantity
            position.avg_entry_price = (
                float(position.avg_entry_price) * float(position.quantity) + fill_price * quantity
            ) / total_qty
            position.quantity = total_qty
        else:
            position = Position(
                org_id=order.org_id,
                mode="paper",
                paper_session_id=session.id,
                instrument_symbol=order.instrument_symbol,
                side=new_side,
                quantity=quantity,
                avg_entry_price=fill_price,
                mark_price=fill_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy_version_id=order.strategy_version_id,
                status="open",
                opened_at=now,
            )
            db.add(position)
            db.flush()
            opened = True
        session.cash_balance = float(session.cash_balance) - fee
        db.add(
            LedgerTransaction(
                org_id=order.org_id,
                type="trade",
                asset=order.fee_currency,
                amount=-notional,
                fee=fee,
                reference_type="order",
                reference_id=order.id,
                occurred_at=now,
                meta={"symbol": order.instrument_symbol, "side": side, "price": fill_price},
            )
        )

    db.add(
        Fee(
            org_id=order.org_id,
            kind=FeeKind.TRADING,
            amount=fee,
            currency=order.fee_currency,
            reference_type="order",
            reference_id=order.id,
            detail={"bps": fee_bps, "model": "paper_taker"},
            occurred_at=now,
        )
    )

    order.status = OrderStatus.FILLED
    order.filled_at = now
    order.filled_qty = quantity
    order.avg_fill_price = fill_price
    order.fee = fee
    order.slippage_actual_bps = slippage_actual_bps
    db.flush()

    # Session equity = cash + mark-to-market of open positions.
    open_positions = (
        db.query(Position)
        .filter(Position.paper_session_id == session.id, Position.status == "open")
        .all()
    )
    equity = float(session.cash_balance)
    for pos in open_positions:
        mark = _mark_price(db, session.id, pos.instrument_symbol, float(pos.mark_price or 0))
        pos.mark_price = mark
        pos.unrealized_pnl = (
            (mark - float(pos.avg_entry_price)) * float(pos.quantity)
            if pos.side == "long"
            else (float(pos.avg_entry_price) - mark) * float(pos.quantity)
        )
        equity += float(pos.unrealized_pnl)
    session.equity = equity
    session.last_tick_at = now
    peak = float((session.config or {}).get("peak_equity") or session.starting_balance)
    session.config = {**(session.config or {}), "peak_equity": max(peak, equity)}
    db.flush()

    notifications.notify(
        db,
        org_id=order.org_id,
        category=NotificationCategory.TRADE,
        severity=Severity.INFO,
        title=(
            f"Paper {'opened' if opened else 'closed'}: {order.instrument_symbol} {side.upper()} "
            f"{quantity:g} @ {fill_price:,.4f}"
        ),
        body=(
            f"Simulated execution. Fee {fee:.4f} {order.fee_currency}, "
            f"slippage {slippage_actual_bps:.1f} bps. Net realised P&L {realized:+.2f} "
            f"{order.fee_currency}. This is demo activity, not a real trade."
        ),
        data={
            "order_id": order.id,
            "trade_id": closed_trade.id if closed_trade else None,
            "session_id": session.id,
            "is_demo": True,
        },
    )

    return FillResult(
        filled_qty=quantity,
        price=fill_price,
        fee=fee,
        slippage_actual_bps=slippage_actual_bps,
        realized_pnl=realized,
        closed_trade=closed_trade,
        position=position,
        opened=opened,
    )
