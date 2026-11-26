"""Order lifecycle gateway.

This module is the only place that turns an intent into an execution. It:
1. resolves tenant-scoped state,
2. builds the immutable ``RiskContext``,
3. asks the independent risk engine for a decision,
4. persists the decision (approved or rejected) for audit,
5. executes only when approved — paper always, live only when every gate passes.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import settings
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.db.constants import (
    AuditAction,
    ConnectionEnvironment,
    Entitlement,
    FeeKind,
    NotificationCategory,
    OrderStatus,
    OrderType,
    Severity,
    TradeMode,
)
from app.db.models import (
    Connection,
    Fee,
    Order,
    PaperSession,
    Position,
    RiskDecision,
    RiskPolicy,
    StrategyVersion,
    Trade,
    TradingPermission,
    User,
)
from app.providers.base import ProviderError
from app.providers.registry import get_provider
from app.risk.engine import engine as risk_engine
from app.risk.types import (
    DEFAULT_RISK_RULES,
    InstrumentView,
    MarketView,
    OrderIntent,
    PositionView,
    RiskContext,
    merged_rules,
)
from app.services import audit, entitlements, kill_switch, market_data, notifications, usage
from app.services.connections import load_credentials
from app.trading import paper
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


@dataclass
class OrderRequest:
    symbol: str
    side: str
    quantity: float
    order_type: str = OrderType.MARKET
    price: float | None = None
    stop_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    mode: str = TradeMode.PAPER
    connection_id: str | None = None
    paper_session_id: str | None = None
    strategy_version_id: str | None = None
    client_order_id: str | None = None
    idempotency_key: str | None = None
    reason: str = ""
    reduce_only: bool = False


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _today_start() -> datetime:
    now = _utcnow()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def active_policy(db: Session, org_id: str) -> RiskPolicy | None:
    org_policy = (
        db.query(RiskPolicy)
        .filter(RiskPolicy.org_id == org_id, RiskPolicy.is_active.is_(True))
        .order_by(RiskPolicy.version.desc())
        .first()
    )
    if org_policy:
        return org_policy
    return (
        db.query(RiskPolicy)
        .filter(RiskPolicy.org_id.is_(None), RiskPolicy.is_active.is_(True))
        .order_by(RiskPolicy.version.desc())
        .first()
    )


def _paper_session_for(db: Session, user: User, session_id: str | None) -> PaperSession:
    if session_id:
        session = db.get(PaperSession, session_id)
        if session is None or session.org_id != user.org_id:
            raise not_found("session_not_found", "Paper session not found.")
        if session.status != "running":
            raise bad_request("session_not_running", "This paper session is not running.")
        return session
    session = (
        db.query(PaperSession)
        .filter(PaperSession.org_id == user.org_id, PaperSession.status == "running")
        .order_by(PaperSession.created_at.desc())
        .first()
    )
    if session is None:
        session = PaperSession(
            org_id=user.org_id,
            strategy_version_id=None,
            instrument_symbol="BTC/USDT",
            timeframe="1h",
            status="running",
            starting_balance=settings.paper_starting_balance,
            cash_balance=settings.paper_starting_balance,
            equity=settings.paper_starting_balance,
            config={"peak_equity": settings.paper_starting_balance, "label": "Manual paper session"},
        )
        db.add(session)
        db.flush()
    return session


def _equity_and_positions(
    db: Session, user: User, mode: str, session: PaperSession | None
) -> tuple[float, float, list[Position], float]:
    query = db.query(Position).filter(Position.org_id == user.org_id, Position.status == "open")
    if mode == TradeMode.PAPER:
        if session is not None:
            query = query.filter(Position.paper_session_id == session.id)
        else:
            query = query.filter(Position.mode == "paper")
    else:
        query = query.filter(Position.mode == "live")
    positions = query.all()
    exposure = 0.0
    unrealised = 0.0
    for p in positions:
        exposure += abs(float(p.quantity) * float(p.mark_price or p.avg_entry_price))
        unrealised += float(p.unrealized_pnl or 0)
    if mode == TradeMode.PAPER and session is not None:
        equity = float(session.equity or session.starting_balance)
    else:
        from app.db.models import Balance
        from sqlalchemy import func

        total = db.query(func.coalesce(func.sum(Balance.usd_value), 0)).filter(Balance.org_id == user.org_id).scalar()
        equity = float(total or 0.0)
    return equity, exposure, positions, unrealised


def _budget(label: str, used: float, cap: float, unit: str) -> dict:
    pct = (used / cap * 100.0) if cap > 0 else 0.0
    state = "blocked" if used >= cap else "warning" if pct >= 80 else "ok"
    return {
        "label": label,
        "used": round(used, 4),
        "cap": round(cap, 4),
        "used_pct": round(min(pct, 999.0), 2),
        "remaining": round(max(cap - used, 0.0), 4),
        "unit": unit,
        "state": state,
    }


def risk_budget(db: Session, user: User) -> dict:
    """Read-only view of how much risk headroom is left before the engine blocks entries.

    Mirrors the arithmetic of the blocking rules exactly, so a trader sees the same
    numbers the engine will use on the next order. It cannot approve or place anything.
    """
    session = paper_session_for(db, user, None)
    policy = active_policy(db, user.org_id)
    rules = merged_rules(policy.rules if policy else None)
    equity, exposure, positions, unrealised = _equity_and_positions(db, user, TradeMode.PAPER, session)

    today_trades = (
        db.query(Trade)
        .filter(Trade.org_id == user.org_id, Trade.closed_at >= _today_start(), Trade.mode == TradeMode.PAPER)
        .all()
    )
    realized_today = sum(float(t.net_pnl) for t in today_trades)
    recent = (
        db.query(Trade)
        .filter(Trade.org_id == user.org_id, Trade.mode == TradeMode.PAPER)
        .order_by(Trade.closed_at.desc())
        .limit(10)
        .all()
    )
    consecutive_losses = 0
    last_loss_at = None
    for trade in recent:
        if float(trade.net_pnl) < 0:
            consecutive_losses += 1
            if last_loss_at is None:
                last_loss_at = trade.closed_at
        else:
            break

    peak = float((session.config or {}).get("peak_equity") or 0) if session else 0.0
    peak = max(peak, equity)
    drawdown_pct = ((peak - equity) / peak * 100.0) if peak > 0 else 0.0
    daily_loss = -(realized_today + min(unrealised, 0.0))

    demo_limit = entitlements.numeric_limit(db, user.org_id, Entitlement.MAX_DAILY_DEMO_EXECUTIONS)
    demo_used = int(usage.get_usage(db, user.org_id, "demo_executions"))

    budgets = [
        _budget("Daily loss", daily_loss, equity * float(rules["daily_loss_limit_pct"]) / 100.0, "usd"),
        _budget("Drawdown", drawdown_pct, float(rules["max_drawdown_pct"]), "pct"),
        _budget(
            "Account exposure",
            (exposure / equity * 100.0) if equity > 0 else 0.0,
            float(rules["max_account_exposure_pct"]),
            "pct",
        ),
        _budget("Open positions", float(len(positions)), float(rules["max_open_positions"]), "count"),
        _budget("Consecutive losses", float(consecutive_losses), float(rules["max_consecutive_losses"]), "count"),
    ]
    if demo_limit is not None:
        budgets.append(_budget("Demo executions today", float(demo_used), float(demo_limit), "count"))

    switches = kill_switch.state_for(db, user.org_id, user_id=user.id)
    blocked = [b["label"] for b in budgets if b["state"] == "blocked"]
    if any(switches.values()):
        blocked.append("Kill switch")

    return {
        "mode": "paper",
        "equity": round(equity, 2),
        "exposure": round(exposure, 2),
        "unrealized_pnl": round(unrealised, 2),
        "realized_pnl_today": round(realized_today, 2),
        "peak_equity": round(peak, 2),
        "open_positions": len(positions),
        "budgets": budgets,
        "blocked": blocked,
        "state": "blocked" if blocked else ("warning" if any(b["state"] == "warning" for b in budgets) else "ok"),
        "kill_switches": switches,
        "policy_id": policy.id if policy else None,
        "policy_version": policy.version if policy else None,
        "notice": "Paper only. A blocked budget means the risk engine will reject new entries, not that anything was closed.",
    }


def build_context(
    db: Session,
    *,
    user: User,
    intent: OrderIntent,
    connection: Connection | None,
    session: PaperSession | None,
    snapshot: market_data.MarketSnapshot,
    venue_demo: bool = False,
    venue_instrument: dict | None = None,
    market_open: bool | None = None,
) -> RiskContext:
    policy = active_policy(db, user.org_id)
    rules = merged_rules(policy.rules if policy else None)
    equity, exposure, positions, unrealised = _equity_and_positions(db, user, intent.mode, session)

    permission = (
        db.query(TradingPermission)
        .filter(TradingPermission.org_id == user.org_id, TradingPermission.status == "active")
        .order_by(TradingPermission.authorized_at.desc())
        .first()
    )
    switches = kill_switch.state_for(
        db, user.org_id, provider=connection.provider if connection else None, user_id=user.id
    )

    today_trades = (
        db.query(Trade)
        .filter(Trade.org_id == user.org_id, Trade.closed_at >= _today_start(), Trade.mode == intent.mode)
        .all()
    )
    realized_today = sum(float(t.net_pnl) for t in today_trades)
    recent = (
        db.query(Trade)
        .filter(Trade.org_id == user.org_id, Trade.mode == intent.mode)
        .order_by(Trade.closed_at.desc())
        .limit(10)
        .all()
    )
    consecutive_losses = 0
    last_loss_at = None
    for t in recent:
        if float(t.net_pnl) < 0:
            consecutive_losses += 1
            if last_loss_at is None:
                last_loss_at = t.closed_at
        else:
            break

    spec = market_data.instrument_spec(intent.symbol) or {}
    duplicate = (
        db.query(Order)
        .filter(
            Order.org_id == user.org_id,
            Order.idempotency_key == intent.idempotency_key,
            Order.status.in_([OrderStatus.INTENT, OrderStatus.SUBMITTED, OrderStatus.OPEN, OrderStatus.FILLED]),
        )
        .first()
        is not None
    )
    if not duplicate and intent.client_order_id:
        duplicate = (
            db.query(Order)
            .filter(
                Order.org_id == user.org_id,
                Order.client_order_id == intent.client_order_id,
            )
            .first()
            is not None
        )

    demo_limit = entitlements.numeric_limit(db, user.org_id, Entitlement.MAX_DAILY_DEMO_EXECUTIONS)
    executions_today = int(usage.get_usage(db, user.org_id, "demo_executions"))

    peak = 0.0
    if session is not None:
        peak = float((session.config or {}).get("peak_equity") or 0)
    peak = max(peak, equity)

    org_suspended = False
    from app.db.models import Organization

    org = db.get(Organization, user.org_id)
    if org:
        org_suspended = bool(org.suspended)

    return RiskContext(
        now=_utcnow(),
        mode=intent.mode,  # type: ignore[arg-type]
        policy=policy.rules if policy else DEFAULT_RISK_RULES,
        policy_id=policy.id if policy else None,
        policy_version=policy.version if policy else 1,
        global_live_enabled=settings.live_trading_enabled,
        org_live_authorized=bool(permission and permission.live_enabled),
        org_live_entitlement=entitlements.has_feature(db, user.org_id, Entitlement.LIVE_TRADING),
        org_suspended=org_suspended,
        kill_global=switches["global"],
        kill_org=switches["org"],
        kill_provider=switches["provider"],
        kill_user=switches["user"],
        connection_trade_permission=bool(connection and connection.permissions.get("trade")),
        connection_read_only=(
            connection is None
            or connection.environment == ConnectionEnvironment.READ_ONLY
            or not bool(connection.permissions.get("trade"))
        ),
        venue_demo=venue_demo,
        equity=equity,
        cash=float(session.cash_balance) if session else equity,
        peak_equity=peak,
        realized_pnl_today=realized_today,
        unrealized_pnl=unrealised,
        consecutive_losses=consecutive_losses,
        last_loss_at=last_loss_at,
        positions=[
            PositionView(
                symbol=p.instrument_symbol,
                side=p.side,
                quantity=float(p.quantity),
                notional=abs(float(p.quantity) * float(p.mark_price or p.avg_entry_price)),
                unrealized_pnl=float(p.unrealized_pnl or 0),
                stop_loss=float(p.stop_loss) if p.stop_loss else None,
            )
            for p in positions
        ],
        account_exposure=exposure,
        portfolio_exposure=exposure,
        open_position_count=len(positions),
        # A venue connection prices instruments the platform's own registry does not list.
        # The venue's symbol catalogue is then the authority on tradability; the platform's
        # symbol specs remain authoritative for every non-venue order.
        instrument=InstrumentView(
            symbol=intent.symbol,
            asset_class=(venue_instrument or spec).get("asset_class", "crypto"),
            min_qty=float((venue_instrument or spec).get("min_qty", 0) or 0),
            qty_step=float((venue_instrument or spec).get("qty_step", spec.get("step", 0)) or 0),
            max_leverage=float(rules.get("max_leverage", 1)),
            is_active=bool(venue_instrument) or spec != {},
        ),
        market=MarketView(
            price=snapshot.price,
            bid=snapshot.bid,
            ask=snapshot.ask,
            as_of=datetime.fromtimestamp(snapshot.ts / 1000, tz=UTC),
            age_seconds=snapshot.age_seconds,
            spread_bps=snapshot.spread_bps,
            source=snapshot.source,
        ),
        duplicate_exists=duplicate,
        executions_today=executions_today,
        daily_execution_limit=demo_limit,
        # Venue connections report the session themselves; the platform's calendar only
        # covers instruments in its own registry.
        market_open=(market_data.is_market_open(intent.symbol) if market_open is None else bool(market_open)),
        is_demo_feed=snapshot.is_demo,
    )


def paper_session_for(db: Session, user: User, session_id: str | None = None) -> PaperSession:
    """Public alias: resolve (or lazily create) the caller's running paper session."""
    return _paper_session_for(db, user, session_id)


def submit_order(db: Session, *, user: User, request: OrderRequest, source: str = "ai_strategy") -> dict:
    if request.mode not in (TradeMode.PAPER, TradeMode.LIVE):
        raise bad_request("invalid_mode", "Mode must be paper or live.")
    spec = market_data.instrument_spec(request.symbol)
    if spec is None:
        raise not_found("instrument_not_found", "Instrument is not supported.")

    # Idempotency: replaying the same key returns the original order, never a second fill.
    idempotency_key = request.idempotency_key or f"auto:{user.org_id}:{uuid.uuid4().hex}"
    existing = db.query(Order).filter(Order.org_id == user.org_id, Order.idempotency_key == idempotency_key).first()
    if existing:
        decision = db.get(RiskDecision, existing.risk_decision_id) if existing.risk_decision_id else None
        return {
            "idempotent_replay": True,
            "order": existing,
            "decision": decision,
            "fill": None,
            "trade": None,
        }

    connection: Connection | None = None
    if request.connection_id:
        connection = db.get(Connection, request.connection_id)
        if connection is None or connection.org_id != user.org_id:
            raise not_found("connection_not_found", "Connection not found.")
        if connection.status == "revoked":
            raise bad_request("connection_revoked", "This connection has been revoked.")
    elif request.mode == TradeMode.LIVE:
        raise bad_request("connection_required", "Live orders require a connected account.")

    session: PaperSession | None = None
    if request.mode == TradeMode.PAPER:
        session = _paper_session_for(db, user, request.paper_session_id)

    strategy_status = None
    if request.strategy_version_id:
        version = db.get(StrategyVersion, request.strategy_version_id)
        if version is None:
            raise not_found("strategy_version_not_found", "Strategy version not found.")
        strategy_status = version.status

    snapshot = market_data.get_ticker(request.symbol)

    intent = OrderIntent(
        org_id=user.org_id,
        mode=request.mode,  # type: ignore[arg-type]
        symbol=request.symbol,
        side=request.side,  # type: ignore[arg-type]
        quantity=float(request.quantity),
        order_type=request.order_type,
        price=request.price,
        stop_price=request.stop_price,
        stop_loss=request.stop_loss,
        take_profit=request.take_profit,
        strategy_version_id=request.strategy_version_id,
        strategy_status=strategy_status,
        client_order_id=request.client_order_id or f"co-{uuid.uuid4().hex[:20]}",
        idempotency_key=idempotency_key,
        reason=request.reason,
        source=source,
        reduce_only=request.reduce_only,
    )
    context = build_context(db, user=user, intent=intent, connection=connection, session=session, snapshot=snapshot)
    assessment = risk_engine.evaluate(intent, context)

    order = Order(
        org_id=user.org_id,
        mode=request.mode,
        connection_id=connection.id if connection else None,
        paper_session_id=session.id if session else None,
        instrument_symbol=request.symbol,
        side=request.side,
        order_type=request.order_type,
        quantity=float(request.quantity),
        price=request.price,
        stop_price=request.stop_price,
        time_in_force="gtc",
        status=OrderStatus.INTENT if assessment.approved else OrderStatus.REJECTED,
        client_order_id=intent.client_order_id,
        idempotency_key=idempotency_key,
        strategy_version_id=request.strategy_version_id,
        correlation_id=uuid.uuid4().hex,
        rejection_reason=None if assessment.approved else "; ".join(f.message for f in assessment.failed),
        slippage_est_bps=settings.paper_slippage_bps + settings.paper_spread_bps / 2
        if request.mode == TradeMode.PAPER
        else 0,
        is_demo=request.mode == TradeMode.PAPER,
    )
    db.add(order)
    db.flush()

    decision = RiskDecision(
        org_id=user.org_id,
        order_intent=intent.as_dict(),
        decision="approved" if assessment.approved else "rejected",
        failed_rules=[f.as_dict() for f in assessment.failed],
        checks=[c.as_dict() for c in assessment.checks],
        policy_id=assessment.policy_id,
        policy_version=assessment.policy_version,
        order_id=order.id,
        correlation_id=order.correlation_id,
    )
    db.add(decision)
    db.flush()
    order.risk_decision_id = decision.id

    audit.record(
        db,
        action=AuditAction.ORDER_INTENT,
        org_id=user.org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        target_type="order",
        target_id=order.id,
        meta={
            "symbol": request.symbol,
            "side": request.side,
            "quantity": request.quantity,
            "mode": request.mode,
            "source": source,
            "market_source": snapshot.source,
            "is_demo_feed": snapshot.is_demo,
        },
    )

    if not assessment.approved:
        audit.record(
            db,
            action=AuditAction.ORDER_REJECTED,
            org_id=user.org_id,
            actor_user_id=user.id,
            target_type="order",
            target_id=order.id,
            meta={"failed_rules": assessment.failed_codes},
        )
        notifications.notify(
            db,
            org_id=user.org_id,
            category=NotificationCategory.ORDER,
            severity=Severity.WARNING,
            title=f"Order rejected: {request.symbol} {request.side}",
            body=order.rejection_reason or "The risk engine rejected this order.",
            data={"order_id": order.id, "failed_rules": assessment.failed_codes},
            email=request.mode == TradeMode.LIVE,
        )
        db.commit()
        return {"idempotent_replay": False, "order": order, "decision": decision, "fill": None, "trade": None}

    if request.mode == TradeMode.PAPER:
        assert session is not None
        fill = paper.execute_market_order(
            db,
            order=order,
            session=session,
            reference_price=snapshot.price,
            side=request.side,
            quantity=float(request.quantity),
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            entry_reason=request.reason,
            risk_snapshot={
                "decision": "approved",
                "policy_version": assessment.policy_version,
                "checks_passed": [c.code for c in assessment.checks if c.passed],
                "market_source": snapshot.source,
                "is_demo_feed": snapshot.is_demo,
                "is_demo_trade": True,
            },
        )
        usage.increment_usage(db, user.org_id, "demo_executions", 1, meta={"last_order_id": order.id})
        audit.record(
            db,
            action=AuditAction.ORDER_FILLED,
            org_id=user.org_id,
            actor_user_id=user.id,
            target_type="order",
            target_id=order.id,
            meta={
                "fill_price": fill.price,
                "fee": fill.fee,
                "slippage_bps": fill.slippage_actual_bps,
                "realized_pnl": fill.realized_pnl,
                "is_demo": True,
            },
        )
        if fill.closed_trade:
            audit.record(
                db,
                action=AuditAction.TRADE_CLOSED,
                org_id=user.org_id,
                actor_user_id=user.id,
                target_type="trade",
                target_id=fill.closed_trade.id,
                meta={"net_pnl": fill.closed_trade.net_pnl, "is_demo": True},
            )
        base_asset = request.symbol.split("/")[0]
        notifications.notify(
            db,
            org_id=user.org_id,
            category=NotificationCategory.ORDER,
            severity=Severity.INFO,
            title=f"Simulated fill: {request.symbol} {request.side.upper()}",
            body=(
                f"Paper order filled at {fill.price} for {request.quantity} {base_asset}. "
                f"Fee {fill.fee:.4f}. Simulated execution — no real funds moved."
            ),
            data={
                "order_id": order.id,
                "trade_id": fill.closed_trade.id if fill.closed_trade else None,
                "is_demo": True,
            },
        )
        if fill.closed_trade:
            trade = fill.closed_trade
            notifications.notify(
                db,
                org_id=user.org_id,
                category=NotificationCategory.TRADE,
                severity=Severity.SUCCESS if trade.net_pnl >= 0 else Severity.WARNING,
                title=f"Simulated trade closed: {request.symbol}",
                body=(
                    f"Net P&L after fees {trade.net_pnl:+.2f} {base_asset} (gross {trade.gross_pnl:+.2f}, "
                    f"fees {trade.fees:.2f}). Realised in paper mode only."
                ),
                data={"trade_id": trade.id, "is_demo": True},
            )
        db.commit()
        return {
            "idempotent_replay": False,
            "order": order,
            "decision": decision,
            "fill": fill,
            "trade": fill.closed_trade,
        }

    # ------------------------- live path -------------------------
    # Re-check the process-wide switch immediately before any venue call (defence in depth).
    if not settings.live_trading_enabled:
        order.status = OrderStatus.REJECTED
        order.rejection_reason = "Live trading is disabled by platform policy."
        db.flush()
        audit.record(
            db,
            action=AuditAction.ORDER_REJECTED,
            org_id=user.org_id,
            actor_user_id=user.id,
            target_type="order",
            target_id=order.id,
            meta={"reason": "platform_live_disabled"},
        )
        db.commit()
        raise forbidden("live_trading_disabled", "Live trading is disabled platform-wide. No order was sent.")
    assert connection is not None
    provider = get_provider(connection.provider)
    order.status = OrderStatus.SUBMITTED
    order.submitted_at = _utcnow()
    db.flush()
    try:
        credentials = load_credentials(db, connection)
        result = provider.place_order(
            credentials,
            {
                "symbol": request.symbol,
                "side": request.side,
                "quantity": request.quantity,
                "order_type": request.order_type,
                "price": request.price,
                "stop_loss": request.stop_loss,
            },
        )
    except ProviderError as exc:
        order.status = OrderStatus.FAILED
        order.rejection_reason = exc.message[:1000]
        db.flush()
        audit.record(
            db,
            action=AuditAction.ORDER_FAILED,
            org_id=user.org_id,
            actor_user_id=user.id,
            target_type="order",
            target_id=order.id,
            meta={"code": exc.code, "message": exc.message},
        )
        notifications.notify(
            db,
            org_id=user.org_id,
            category=NotificationCategory.ORDER,
            severity=Severity.CRITICAL,
            title=f"Live order failed: {request.symbol}",
            body=exc.message,
            email=True,
        )
        db.commit()
        raise bad_request(exc.code, exc.message) from exc
    order.provider_order_id = result.get("provider_order_id")
    order.status = OrderStatus.FILLED if float(result.get("filled") or 0) > 0 else OrderStatus.OPEN
    order.filled_qty = float(result.get("filled") or 0)
    order.avg_fill_price = result.get("average") or None
    order.fee = float(result.get("fee") or 0)
    order.is_demo = False
    if order.status == OrderStatus.FILLED:
        order.filled_at = _utcnow()
    db.add(
        Fee(
            org_id=user.org_id,
            kind=FeeKind.TRADING,
            amount=order.fee,
            currency=order.fee_currency,
            reference_type="order",
            reference_id=order.id,
            detail={"provider": connection.provider},
            occurred_at=_utcnow(),
        )
    )
    db.flush()
    audit.record(
        db,
        action=AuditAction.ORDER_SUBMITTED,
        org_id=user.org_id,
        actor_user_id=user.id,
        target_type="order",
        target_id=order.id,
        meta={"provider_order_id": order.provider_order_id, "status": order.status},
    )
    notifications.notify(
        db,
        org_id=user.org_id,
        category=NotificationCategory.ORDER,
        severity=Severity.CRITICAL,
        title=f"LIVE order {order.status}: {request.symbol} {request.side}",
        body=f"Submitted to {connection.provider}. Venue order id {order.provider_order_id}.",
        email=True,
    )
    db.commit()
    return {"idempotent_replay": False, "order": order, "decision": decision, "fill": None, "trade": None}


def close_position(db: Session, *, user: User, position: Position, reason: str, note: str | None = None) -> dict:
    if position.org_id != user.org_id:
        raise not_found("position_not_found", "Position not found.")
    if position.status != "open":
        raise conflict("position_closed", "This position is already closed.")
    side = "sell" if position.side == "long" else "buy"
    result = submit_order(
        db,
        user=user,
        request=OrderRequest(
            symbol=position.instrument_symbol,
            side=side,
            quantity=float(position.quantity),
            mode=position.mode,
            paper_session_id=position.paper_session_id,
            strategy_version_id=position.strategy_version_id,
            reason=reason or "Manual close requested by user",
            reduce_only=True,
        ),
        source="human",
    )
    trade = result.get("trade")
    if trade:
        trade.human_intervention = True
        trade.intervention_note = note or "Closed manually from the trading terminal."
        db.commit()
    return result


def cancel_order(db: Session, *, user: User, order: Order) -> Order:
    if order.org_id != user.org_id:
        raise not_found("order_not_found", "Order not found.")
    if order.status not in (OrderStatus.INTENT, OrderStatus.SUBMITTED, OrderStatus.OPEN):
        raise conflict("order_not_cancellable", f"Order is {order.status} and cannot be cancelled.")
    if order.mode == TradeMode.LIVE and order.provider_order_id and order.connection_id:
        connection = db.get(Connection, order.connection_id)
        if connection:
            provider = get_provider(connection.provider)
            try:
                provider.cancel_order(
                    load_credentials(db, connection), order.provider_order_id, order.instrument_symbol
                )
            except ProviderError as exc:
                raise bad_request(exc.code, exc.message) from exc
    order.status = OrderStatus.CANCELED
    db.flush()
    audit.record(
        db,
        action=AuditAction.ORDER_INTENT,
        org_id=user.org_id,
        actor_user_id=user.id,
        target_type="order",
        target_id=order.id,
        meta={"action": "cancelled"},
    )
    return order


def flatten_paper_positions(db: Session, *, user: User, reason: str = "Kill switch flatten") -> dict:
    positions = (
        db.query(Position)
        .filter(Position.org_id == user.org_id, Position.mode == "paper", Position.status == "open")
        .all()
    )
    closed, failed = 0, []
    for pos in positions:
        try:
            close_position(db, user=user, position=pos, reason=reason)
            closed += 1
        except Exception as exc:  # noqa: BLE001
            failed.append({"position": pos.id, "error": str(exc)[:200]})
    return {"closed": closed, "failed": failed}
