from __future__ import annotations

from app.db.models import (
    Backtest,
    BinaryContract,
    Connection,
    ConnectionCredential,
    Fee,
    Order,
    PaperSession,
    Position,
    RiskDecision,
    Strategy,
    StrategyVersion,
    Trade,
)
from sqlalchemy.orm import Session


def iso(value) -> str | None:
    return value.isoformat() if value else None


def num(value, digits: int = 8):
    if value is None:
        return None
    return float(round(float(value), digits))


def user_dict(user) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "org_id": user.org_id,
        "status": user.status,
        "email_verified": user.email_verified_at is not None,
        "mfa_enabled": user.mfa_enabled,
        "is_staff": user.is_staff,
        "staff_role": user.staff_role,
        "onboarding_step": user.onboarding_step,
        "risk_profile": user.risk_profile or {},
        "preferences": user.preferences or {},
        "last_login_at": iso(user.last_login_at),
        "created_at": iso(user.created_at),
        "terms_version": user.terms_version,
    }


def org_dict(org) -> dict:
    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "country": org.country,
        "timezone": org.timezone,
        "onboarding": org.onboarding or {},
        "created_at": iso(org.created_at),
    }


def decision_dict(decision: RiskDecision | None) -> dict | None:
    if decision is None:
        return None
    return {
        "id": decision.id,
        "decision": decision.decision,
        "failed_rules": decision.failed_rules,
        "checks": decision.checks,
        "policy_id": decision.policy_id,
        "policy_version": decision.policy_version,
        "created_at": iso(decision.created_at),
    }


def order_dict(order: Order, decision: RiskDecision | None = None) -> dict:
    return {
        "id": order.id,
        "mode": order.mode,
        "is_demo": order.is_demo,
        "symbol": order.instrument_symbol,
        "side": order.side,
        "order_type": order.order_type,
        "quantity": num(order.quantity),
        "price": num(order.price),
        "stop_price": num(order.stop_price),
        "status": order.status,
        "client_order_id": order.client_order_id,
        "strategy_version_id": order.strategy_version_id,
        "connection_id": order.connection_id,
        "paper_session_id": order.paper_session_id,
        "rejection_reason": order.rejection_reason,
        "filled_qty": num(order.filled_qty),
        "avg_fill_price": num(order.avg_fill_price),
        "fee": num(order.fee),
        "fee_currency": order.fee_currency,
        "slippage_est_bps": num(order.slippage_est_bps, 2),
        "slippage_actual_bps": num(order.slippage_actual_bps, 2),
        "provider_order_id": order.provider_order_id,
        "correlation_id": order.correlation_id,
        "created_at": iso(order.created_at),
        "submitted_at": iso(order.submitted_at),
        "filled_at": iso(order.filled_at),
        "risk_decision": decision_dict(decision),
    }


def trade_dict(trade: Trade) -> dict:
    return {
        "id": trade.id,
        "order_id": trade.order_id,
        "mode": trade.mode,
        "is_demo": trade.is_demo,
        "symbol": trade.instrument_symbol,
        "side": trade.side,
        "quantity": num(trade.quantity),
        "entry_price": num(trade.entry_price),
        "exit_price": num(trade.exit_price),
        "notional": num(trade.notional, 2),
        "fees": num(trade.fees, 4),
        "funding": num(trade.funding, 4),
        "slippage_est_bps": num(trade.slippage_est_bps, 2),
        "slippage_actual_bps": num(trade.slippage_actual_bps, 2),
        "gross_pnl": num(trade.gross_pnl, 2),
        "net_pnl": num(trade.net_pnl, 2),
        "entry_reason": trade.entry_reason,
        "exit_reason": trade.exit_reason,
        "strategy_version_id": trade.strategy_version_id,
        "human_intervention": trade.human_intervention,
        "intervention_note": trade.intervention_note,
        "opened_at": iso(trade.opened_at),
        "closed_at": iso(trade.closed_at),
        "risk_snapshot": trade.risk_snapshot,
    }


def _trade_risk_decision(db: Session, trade: Trade) -> RiskDecision | None:
    if trade.order_id:
        order = db.get(Order, trade.order_id)
        if order and order.risk_decision_id:
            return db.get(RiskDecision, order.risk_decision_id)
    contract = db.query(BinaryContract).filter(BinaryContract.trade_id == trade.id).first()
    if contract and contract.risk_decision_id:
        return db.get(RiskDecision, contract.risk_decision_id)
    return None


def trade_detail(db: Session, trade: Trade) -> dict:
    data = trade_dict(trade)
    order = db.get(Order, trade.order_id) if trade.order_id else None
    decision = _trade_risk_decision(db, trade)
    version = db.get(StrategyVersion, trade.strategy_version_id) if trade.strategy_version_id else None
    strategy = db.get(Strategy, version.strategy_id) if version else None
    fees = db.query(Fee).filter(Fee.reference_id == trade.order_id).all() if trade.order_id else []
    data.update(
        {
            "order": order_dict(order, decision) if order else None,
            # Binary contracts have no order row; their decision still belongs to the trade.
            "risk_decision": None if order else decision_dict(decision),
            "strategy": (
                {
                    "code": strategy.code,
                    "name": strategy.name,
                    "version": version.version,
                    "status": version.status,
                    "known_limitations": version.known_limitations,
                }
                if version and strategy
                else None
            ),
            "fees_breakdown": [
                {
                    "kind": f.kind,
                    "amount": num(f.amount, 4),
                    "currency": f.currency,
                    "detail": f.detail,
                    "occurred_at": iso(f.occurred_at),
                }
                for f in fees
            ],
            "risk_snapshot": trade.risk_snapshot,
            "cost_summary": {
                "gross_pnl": num(trade.gross_pnl, 2),
                "fees": num(trade.fees, 4),
                "funding": num(trade.funding, 4),
                "net_pnl": num(trade.net_pnl, 2),
                "slippage_est_bps": num(trade.slippage_est_bps, 2),
                "slippage_actual_bps": num(trade.slippage_actual_bps, 2),
            },
        }
    )
    return data


def position_dict(position: Position) -> dict:
    return {
        "id": position.id,
        "mode": position.mode,
        "symbol": position.instrument_symbol,
        "side": position.side,
        "quantity": num(position.quantity),
        "avg_entry_price": num(position.avg_entry_price),
        "mark_price": num(position.mark_price),
        "unrealized_pnl": num(position.unrealized_pnl, 2),
        "realized_pnl": num(position.realized_pnl, 2),
        "leverage": num(position.leverage, 2),
        "stop_loss": num(position.stop_loss),
        "take_profit": num(position.take_profit),
        "strategy_version_id": position.strategy_version_id,
        "status": position.status,
        "connection_id": position.connection_id,
        "paper_session_id": position.paper_session_id,
        "opened_at": iso(position.opened_at),
        "closed_at": iso(position.closed_at),
    }


def session_dict(session: PaperSession) -> dict:
    return {
        "id": session.id,
        "status": session.status,
        "strategy_version_id": session.strategy_version_id,
        "symbol": session.instrument_symbol,
        "timeframe": session.timeframe,
        "starting_balance": num(session.starting_balance, 2),
        "cash_balance": num(session.cash_balance, 2),
        "equity": num(session.equity, 2),
        "config": session.config or {},
        "last_tick_at": iso(session.last_tick_at),
        "started_at": iso(session.created_at),
        "stopped_at": iso(session.stopped_at),
        "is_demo": True,
    }


def backtest_dict(backtest: Backtest, include_curve: bool = False) -> dict:
    data = {
        "id": backtest.id,
        "strategy_version_id": backtest.strategy_version_id,
        "symbol": backtest.instrument_symbol,
        "timeframe": backtest.timeframe,
        "start_at": iso(backtest.start_at),
        "end_at": iso(backtest.end_at),
        "params": backtest.params,
        "cost_model": backtest.cost_model,
        "status": backtest.status,
        "metrics": backtest.metrics,
        "trades_count": backtest.trades_count,
        "data_source": backtest.data_source,
        "engine_version": backtest.engine_version,
        "error": backtest.error,
        "created_at": iso(backtest.created_at),
        "completed_at": iso(backtest.completed_at),
    }
    if include_curve:
        data["equity_curve"] = backtest.equity_curve
    return data


def connection_dict(connection: Connection, credential: ConnectionCredential | None = None) -> dict:
    from app.services.connections import serialise

    return serialise(connection, credential)
