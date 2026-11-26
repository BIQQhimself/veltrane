"""Automation for Deriv connections: signals, approval and execution.

Two modes, both subordinate to the execution gate and the risk engine:

* ``approval`` — the runner writes a signal and waits. A human approves; only then does the
  order reach Deriv.
* ``autonomous`` — the runner executes its own signal through the same gate and risk engine,
  with no bypass path. Autonomous mode cannot be enabled unless the gate passes.

The baseline strategy is deliberately plain and fully documented in
``app/trading/deriv_strategy.py``. It is not a profit claim; it is a deterministic technical
trigger whose results, after venue costs, are what they are.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from app.core.errors import bad_request, forbidden
from app.db.constants import AuditAction
from app.db.models import AutoTradeConfig, AutoTradeSignal, Connection, Order, User
from app.services import audit, deriv_sessions, execution_gate, kill_switch
from app.trading import deriv_execution
from app.trading.deriv_strategy import evaluate_entry
from sqlalchemy import func
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def daily_stake_used(db: Session, connection: Connection) -> float:
    since = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    total = (
        db.query(func.coalesce(func.sum(Order.quantity), 0))
        .filter(
            Order.connection_id == connection.id,
            Order.created_at >= since,
            Order.status.in_(("filled", "closed")),
        )
        .scalar()
    )
    # quantity is stake/price, so recover the stake from the stored meta when available.
    rows = (
        db.query(Order)
        .filter(
            Order.connection_id == connection.id,
            Order.created_at >= since,
            Order.status.in_(("filled", "closed")),
        )
        .all()
    )
    stake = sum(float((row.meta or {}).get("stake") or 0) for row in rows)
    return round(stake or float(total or 0), 2)


def daily_realized(db: Session, connection: Connection) -> float:
    since = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (
        db.query(Order)
        .filter(Order.connection_id == connection.id, Order.created_at >= since, Order.status == "closed")
        .all()
    )
    return round(sum(float((row.meta or {}).get("realized") or 0) for row in rows), 2)


def _halt_reason(db: Session, config: AutoTradeConfig, connection: Connection, gate) -> str:
    switches = kill_switch.state_for(db, config.org_id, provider=connection.provider)
    engaged = [name for name, on in switches.items() if on]
    if engaged:
        return f"Kill switch engaged: {', '.join(engaged)}"
    if not gate.allowed:
        return gate.blocking_message
    open_orders = (
        db.query(Order)
        .filter(
            Order.connection_id == connection.id,
            Order.status.in_(("submitted", "filled")),
        )
        .count()
    )
    if open_orders >= config.max_open_contracts:
        return f"Open contract limit reached ({config.max_open_contracts})."
    if daily_stake_used(db, connection) + float(config.stake) > float(config.daily_stake_limit):
        return "Daily stake limit reached."
    if daily_realized(db, connection) <= -abs(float(config.daily_loss_limit)):
        return "Daily loss limit reached."
    if config.last_signal_at and (_utcnow() - config.last_signal_at).total_seconds() < config.cooldown_seconds:
        return "Cooldown active."
    return ""


def run_config(db: Session, config: AutoTradeConfig, *, actor: User | None = None) -> dict:
    connection = db.get(Connection, config.connection_id)
    if connection is None or connection.org_id != config.org_id:
        return {"skipped": "connection_missing"}
    owner = db.get(User, connection.created_by) if connection.created_by else None
    if owner is None:
        return {"skipped": "owner_missing"}

    config.last_run_at = _utcnow()
    gate = execution_gate.evaluate(db, user=owner, connection=connection)
    reason = _halt_reason(db, config, connection, gate)
    if reason:
        config.halt_reason = reason
        db.flush()
        return {"skipped": reason}

    adapter = deriv_sessions.adapter()
    try:
        candles = adapter.fetch_ohlcv(config.symbol, "1m", 120)
    except Exception as exc:  # noqa: BLE001 - a venue hiccup must not crash the runner
        config.halt_reason = f"market data unavailable: {exc}"
        db.flush()
        return {"skipped": config.halt_reason}

    decision = evaluate_entry(candles)
    if decision is None:
        config.halt_reason = ""
        db.flush()
        return {"signal": None, "reason": "no setup"}

    signal = AutoTradeSignal(
        org_id=config.org_id,
        connection_id=connection.id,
        config_id=config.id,
        status="pending",
        mode=config.mode,
        symbol=config.symbol,
        side="buy" if decision.contract_type == "CALL" else "sell",
        contract_type=decision.contract_type,
        stake=float(config.stake),
        duration=config.duration,
        duration_unit=config.duration_unit,
        reason=decision.reason,
        risk_snapshot={
            "strategy": decision.strategy,
            "indicators": decision.indicators,
            "gate_checks": gate.checks,
            "generated_at": _utcnow().isoformat(),
        },
        expires_at=_utcnow() + timedelta(seconds=config.signal_ttl_seconds),
    )
    db.add(signal)
    config.last_signal_at = _utcnow()
    config.halt_reason = ""
    db.flush()

    audit.record(
        db,
        action=AuditAction.ORDER_INTENT,
        org_id=config.org_id,
        actor_user_id=actor.id if actor else None,
        target_type="auto_trade_signal",
        target_id=signal.id,
        meta={
            "symbol": signal.symbol,
            "contract_type": signal.contract_type,
            "stake": float(signal.stake),
            "mode": config.mode,
            "strategy": decision.strategy,
        },
    )

    if config.mode != "autonomous":
        return {"signal": signal.id, "status": "pending", "reason": decision.reason}

    try:
        result = execute_signal(db, signal=signal, actor=owner, approved_by=None)
        return {"signal": signal.id, "status": signal.status, "result": result}
    except Exception as exc:  # noqa: BLE001 - record why the autonomous entry did not happen
        signal.status = "failed"
        signal.error = str(exc)[:1000]
        signal.decided_at = _utcnow()
        db.flush()
        return {"signal": signal.id, "status": "failed", "error": signal.error}


def execute_signal(db: Session, *, signal: AutoTradeSignal, actor: User, approved_by: User | None) -> dict:
    if signal.status != "pending":
        raise bad_request("signal_not_pending", f"Signal is already {signal.status}.")
    if signal.expires_at and signal.expires_at < _utcnow():
        signal.status = "expired"
        db.flush()
        raise bad_request("signal_expired", "This signal expired before it was approved.")
    connection = db.get(Connection, signal.connection_id)
    if connection is None or connection.org_id != signal.org_id:
        raise bad_request("connection_missing", "The connection for this signal no longer exists.")

    signal.status = "approved"
    signal.decided_at = _utcnow()
    signal.decided_by = approved_by.id if approved_by else None
    db.flush()

    try:
        result = deriv_execution.open_contract(
            db,
            user=actor,
            connection=connection,
            payload={
                "symbol": signal.symbol,
                "side": signal.side,
                "contract_type": signal.contract_type,
                "stake": float(signal.stake),
                "duration": signal.duration,
                "duration_unit": signal.duration_unit,
            },
            source="ai_strategy",
            reason=signal.reason,
            idempotency_key=f"signal:{signal.id}",
        )
    except Exception as exc:  # noqa: BLE001 - the signal records the refusal
        signal.status = "failed"
        signal.error = str(exc)[:1000]
        db.flush()
        audit.record(
            db,
            action=AuditAction.ORDER_REJECTED,
            org_id=signal.org_id,
            actor_user_id=actor.id,
            target_type="auto_trade_signal",
            target_id=signal.id,
            meta={"error": signal.error},
        )
        raise

    order = result.get("order") or {}
    if not result.get("approved", True):
        # The risk engine refused the contract. The order exists for the audit trail, but this
        # signal produced no venue contract and must never be reported as executed.
        failed = [f.get("message", "") for f in (result.get("risk") or {}).get("failed_rules", [])]
        signal.status = "rejected"
        signal.order_id = order.get("id")
        signal.error = "; ".join(m for m in failed if m)[:1000] or "Rejected by the risk engine."
        db.flush()
        return result

    signal.status = "executed"
    signal.order_id = order.get("id")
    signal.contract_id = (result.get("venue") or {}).get("contract_id")
    signal.error = None
    db.flush()
    return result


def run_once(db: Session) -> dict:
    """One pass over every enabled automation. Called by the scheduler thread."""
    configs = db.query(AutoTradeConfig).filter(AutoTradeConfig.enabled.is_(True)).all()
    results = []
    for config in configs:
        try:
            results.append({"config_id": config.id, **run_config(db, config)})
        except Exception as exc:  # noqa: BLE001 - one bad config must not stop the pass
            log.warning("autotrade_config_failed", extra={"extra_fields": {"config_id": config.id}})
            db.rollback()
            results.append({"config_id": config.id, "error": str(exc)[:300]})
    return {"configs": len(configs), "results": results}


def enable(db: Session, *, user: User, connection: Connection, config: AutoTradeConfig) -> None:
    gate = execution_gate.evaluate(db, user=user, connection=connection)
    if not gate.allowed:
        raise forbidden("execution_blocked", gate.blocking_message)
    config.enabled = True
    db.flush()


def signal_id() -> str:
    return uuid.uuid4().hex
