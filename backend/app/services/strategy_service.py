from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.errors import bad_request, forbidden, not_found
from app.db.constants import AuditAction, Entitlement, NotificationCategory, Severity
from app.db.models import Backtest, PaperSession, Position, Strategy, StrategyVersion, User
from app.services import audit, entitlements, market_data, notifications, usage
from app.strategies.backtest import CostModel, run_backtest as run_backtest_engine, walk_forward
from app.strategies.base import PositionState
from app.strategies.library import LIBRARY, get_strategy
from app.trading.engine import OrderRequest, close_position, submit_order
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def seed_system_strategies(db: Session) -> None:
    for code, strategy in LIBRARY.items():
        record = (
            db.query(Strategy)
            .filter(Strategy.org_id.is_(None), Strategy.code == code)
            .first()
        )
        if record is None:
            record = Strategy(
                org_id=None,
                code=code,
                name=strategy.name,
                category=strategy.category,
                summary=strategy.summary,
                is_system=True,
                enabled=True,
            )
            db.add(record)
            db.flush()
        else:
            record.name = strategy.name
            record.category = strategy.category
            record.summary = strategy.summary
        version = (
            db.query(StrategyVersion)
            .filter(StrategyVersion.strategy_id == record.id, StrategyVersion.version == strategy.version)
            .first()
        )
        payload = {
            "supported_markets": strategy.supported_markets,
            "timeframes": strategy.timeframes,
            "params_schema": strategy.params_schema,
            "default_params": strategy.default_params,
            "entry_rules": strategy.entry_rules,
            "exit_rules": strategy.exit_rules,
            "risk_params": strategy.risk_params,
            "data_requirements": strategy.data_requirements,
            "backtest_methodology": strategy.backtest_methodology,
            "known_limitations": strategy.known_limitations,
            "changelog": "Initial system release.",
        }
        if version is None:
            db.add(
                StrategyVersion(
                    strategy_id=record.id,
                    version=strategy.version,
                    status="approved",
                    requires_approval=True,
                    **payload,
                )
            )
        else:
            for key, value in payload.items():
                setattr(version, key, value)
    db.flush()


def list_available(db: Session, org_id: str) -> list[dict]:
    allowed = set(entitlements.allowed_strategies(db, org_id))
    rows = (
        db.query(Strategy)
        .filter(Strategy.enabled.is_(True))
        .filter((Strategy.org_id.is_(None)) | (Strategy.org_id == org_id))
        .order_by(Strategy.is_system.desc(), Strategy.name)
        .all()
    )
    out = []
    for strategy in rows:
        version = latest_version(db, strategy.id)
        out.append(
            {
                "id": strategy.id,
                "code": strategy.code,
                "name": strategy.name,
                "category": strategy.category,
                "summary": strategy.summary,
                "is_system": strategy.is_system,
                "enabled": strategy.enabled,
                "entitled": strategy.code in allowed,
                "version": version.version if version else None,
                "version_id": version.id if version else None,
                "status": version.status if version else "draft",
                "supported_markets": version.supported_markets if version else [],
                "timeframes": version.timeframes if version else [],
                "default_params": version.default_params if version else {},
                "params_schema": version.params_schema if version else {},
                "entry_rules": version.entry_rules if version else "",
                "exit_rules": version.exit_rules if version else "",
                "data_requirements": version.data_requirements if version else "",
                "backtest_methodology": version.backtest_methodology if version else "",
                "known_limitations": version.known_limitations if version else "",
                "risk_params": version.risk_params if version else {},
            }
        )
    return out


def latest_version(db: Session, strategy_id: str) -> StrategyVersion | None:
    return (
        db.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version.desc())
        .first()
    )


def resolve_strategy(db: Session, org_id: str, code: str) -> tuple[Strategy, StrategyVersion, Strategy]:
    impl = get_strategy(code)
    if impl is None:
        raise not_found("strategy_not_found", "Strategy not found.")
    if not entitlements.strategy_allowed(db, org_id, code):
        raise forbidden("entitlement_required", "Your plan does not include this strategy.")
    record = (
        db.query(Strategy)
        .filter(Strategy.code == code)
        .filter((Strategy.org_id.is_(None)) | (Strategy.org_id == org_id))
        .order_by(Strategy.is_system.desc())
        .first()
    )
    if record is None:
        raise not_found("strategy_not_found", "Strategy is not registered.")
    version = latest_version(db, record.id)
    if version is None:
        raise bad_request("strategy_unversioned", "Strategy has no version record.")
    return impl, version, record


def create_custom_version(
    db: Session, *, user: User, code: str, params: dict, changelog: str
) -> StrategyVersion:
    entitlements.require_feature(
        db, user.org_id, Entitlement.STRATEGY_CUSTOMIZATION, "Strategy customisation requires the Pro or Elite plan."
    )
    impl, base_version, record = resolve_strategy(db, user.org_id, code)
    validated = {}
    for key, spec in (base_version.params_schema or {}).items():
        if key not in params:
            continue
        value = params[key]
        if spec.get("type") == "int":
            value = int(value)
        elif spec.get("type") == "float":
            value = float(value)
        elif spec.get("type") == "bool":
            value = bool(value)
        if "min" in spec and value < spec["min"]:
            raise bad_request("param_out_of_range", f"{key} must be at least {spec['min']}.")
        if "max" in spec and value > spec["max"]:
            raise bad_request("param_out_of_range", f"{key} must be at most {spec['max']}.")
        validated[key] = value
    merged = {**(base_version.default_params or {}), **validated}
    next_version = base_version.version + 1
    version = StrategyVersion(
        strategy_id=record.id,
        version=next_version,
        status="draft",
        supported_markets=base_version.supported_markets,
        timeframes=base_version.timeframes,
        params_schema=base_version.params_schema,
        default_params=merged,
        entry_rules=base_version.entry_rules,
        exit_rules=base_version.exit_rules,
        risk_params=base_version.risk_params,
        data_requirements=base_version.data_requirements,
        backtest_methodology=base_version.backtest_methodology,
        known_limitations=base_version.known_limitations,
        changelog=changelog[:2000] or "Parameter customisation.",
        requires_approval=True,
    )
    db.add(version)
    db.flush()
    audit.record(
        db,
        action=AuditAction.STRATEGY_VERSION_APPROVED,
        org_id=user.org_id,
        actor_user_id=user.id,
        target_type="strategy_version",
        target_id=version.id,
        meta={"action": "created", "version": next_version, "params": merged},
    )
    notifications.notify(
        db,
        org_id=user.org_id,
        category=NotificationCategory.SYSTEM,
        severity=Severity.INFO,
        title=f"Strategy draft created: {record.name} v{next_version}",
        body="Significant strategy changes require your explicit approval before they can be traded.",
    )
    return version


def approve_version(db: Session, *, user: User, version_id: str, acknowledge_risk: bool) -> StrategyVersion:
    version = db.get(StrategyVersion, version_id)
    if version is None:
        raise not_found("strategy_version_not_found", "Strategy version not found.")
    strategy = db.get(Strategy, version.strategy_id)
    if strategy is None or (strategy.org_id is not None and strategy.org_id != user.org_id):
        raise not_found("strategy_version_not_found", "Strategy version not found.")
    if not acknowledge_risk:
        raise bad_request("risk_ack_required", "You must acknowledge the strategy's known limitations.")
    version.status = "approved"
    version.approved_by = user.id
    version.approved_at = _utcnow()
    db.flush()
    audit.record(
        db,
        action=AuditAction.STRATEGY_VERSION_APPROVED,
        org_id=user.org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        target_type="strategy_version",
        target_id=version.id,
        meta={"version": version.version, "strategy": strategy.code},
    )
    return version


def promote_to_live(db: Session, *, actor: User, version_id: str, reason: str) -> StrategyVersion:
    """Operator-only. Marks a version eligible for live routing (still gated elsewhere)."""
    version = db.get(StrategyVersion, version_id)
    if version is None:
        raise not_found("strategy_version_not_found", "Strategy version not found.")
    version.status = "live"
    db.flush()
    audit.record(
        db,
        action=AuditAction.STRATEGY_VERSION_APPROVED,
        actor_user_id=actor.id,
        actor_email=actor.email,
        actor_role=actor.staff_role,
        target_type="strategy_version",
        target_id=version.id,
        meta={"action": "promoted_to_live", "reason": reason},
    )
    return version


def run_backtest(
    db: Session,
    *,
    user: User,
    code: str,
    symbol: str,
    timeframe: str,
    params: dict,
    start: datetime | None = None,
    end: datetime | None = None,
    with_walk_forward: bool = False,
) -> Backtest:
    entitlements.require_feature(
        db, user.org_id, Entitlement.BACKTESTING, "Backtesting requires the Pro or Elite plan."
    )
    daily_limit = entitlements.numeric_limit(db, user.org_id, Entitlement.MAX_BACKTESTS_PER_DAY)
    used = int(usage.get_usage(db, user.org_id, "backtests"))
    if daily_limit is not None and used >= daily_limit:
        raise forbidden("backtest_limit_reached", f"Daily backtest limit of {daily_limit} reached.")

    impl, version, _record = resolve_strategy(db, user.org_id, code)
    if timeframe not in impl.timeframes:
        raise bad_request("unsupported_timeframe", f"{impl.name} supports {', '.join(impl.timeframes)}.")
    candles, meta = market_data.get_candles(symbol, timeframe, 1000)
    if start:
        candles = [c for c in candles if c.ts >= start.timestamp() * 1000]
    if end:
        candles = [c for c in candles if c.ts <= end.timestamp() * 1000]
    if len(candles) < 150:
        raise bad_request(
            "insufficient_history",
            f"Only {len(candles)} candles available for that window. Widen the range or use a larger timeframe.",
        )
    merged_params = {**(version.default_params or {}), **(params or {})}
    costs = CostModel(
        fee_bps=settings.paper_taker_fee_bps,
        spread_bps=settings.paper_spread_bps,
        slippage_bps=settings.paper_slippage_bps,
        starting_equity=settings.paper_starting_balance,
    )
    result = run_backtest_engine(impl, candles, merged_params, timeframe=timeframe, costs=costs, data_meta=meta)
    if with_walk_forward:
        result.metrics["walk_forward"] = walk_forward(
            impl, candles, merged_params, timeframe=timeframe, costs=costs, data_meta=meta
        )
    record = Backtest(
        org_id=user.org_id,
        strategy_version_id=version.id,
        instrument_symbol=symbol,
        timeframe=timeframe,
        start_at=datetime.fromtimestamp(candles[0].ts / 1000, tz=timezone.utc),
        end_at=datetime.fromtimestamp(candles[-1].ts / 1000, tz=timezone.utc),
        params=merged_params,
        cost_model=costs.as_dict(),
        status="completed",
        metrics=result.metrics,
        equity_curve=result.equity_curve,
        trades_count=result.metrics["trades"],
        data_source=meta.get("source", "unknown"),
        engine_version=result.engine_version,
        completed_at=_utcnow(),
    )
    db.add(record)
    db.flush()
    usage.increment_usage(db, user.org_id, "backtests", 1, meta={"last_backtest": record.id})
    audit.record(
        db,
        action=AuditAction.BACKTEST_COMPLETED,
        org_id=user.org_id,
        actor_user_id=user.id,
        target_type="backtest",
        target_id=record.id,
        meta={"strategy": code, "symbol": symbol, "data_source": record.data_source, "is_demo": bool(meta.get("is_demo"))},
    )
    return record


def start_paper_session(
    db: Session, *, user: User, code: str, symbol: str, timeframe: str, params: dict | None = None
) -> PaperSession:
    impl, version, _record = resolve_strategy(db, user.org_id, code)
    if version.status not in ("approved", "live"):
        raise bad_request("strategy_not_approved", "Approve this strategy version before running it.")
    if timeframe not in impl.timeframes:
        raise bad_request("unsupported_timeframe", f"{impl.name} supports {', '.join(impl.timeframes)}.")
    if market_data.instrument_spec(symbol) is None:
        raise not_found("instrument_not_found", "Instrument is not supported.")
    existing = (
        db.query(PaperSession)
        .filter(PaperSession.org_id == user.org_id, PaperSession.status == "running")
        .first()
    )
    if existing:
        raise bad_request("session_running", "A paper session is already running. Stop it first.")
    session = PaperSession(
        org_id=user.org_id,
        strategy_version_id=version.id,
        instrument_symbol=symbol,
        timeframe=timeframe,
        status="running",
        starting_balance=settings.paper_starting_balance,
        cash_balance=settings.paper_starting_balance,
        equity=settings.paper_starting_balance,
        config={
            "peak_equity": settings.paper_starting_balance,
            "params": {**(version.default_params or {}), **(params or {})},
            "strategy_code": code,
            "label": f"{impl.name} · {symbol}",
        },
    )
    db.add(session)
    db.flush()
    audit.record(
        db,
        action="paper_session.started",
        org_id=user.org_id,
        actor_user_id=user.id,
        target_type="paper_session",
        target_id=session.id,
        meta={"strategy": code, "symbol": symbol, "timeframe": timeframe},
    )
    notifications.notify(
        db,
        org_id=user.org_id,
        category=NotificationCategory.SYSTEM,
        severity=Severity.INFO,
        title=f"Paper session started: {impl.name} on {symbol}",
        body="All executions are simulated and labelled as demo activity. No real money is at risk.",
    )
    return session


def stop_paper_session(db: Session, *, user: User, session: PaperSession, close_positions: bool = True) -> PaperSession:
    if session.org_id != user.org_id:
        raise not_found("session_not_found", "Paper session not found.")
    if close_positions:
        positions = (
            db.query(Position)
            .filter(Position.paper_session_id == session.id, Position.status == "open")
            .all()
        )
        for position in positions:
            try:
                close_position(db, user=user, position=position, reason="Paper session stopped by user")
            except Exception as exc:  # noqa: BLE001
                log.warning("paper_close_failed", extra={"extra_fields": {"position": position.id, "error": str(exc)[:200]}})
    session.status = "stopped"
    session.stopped_at = _utcnow()
    db.flush()
    audit.record(
        db,
        action="paper_session.stopped",
        org_id=user.org_id,
        actor_user_id=user.id,
        target_type="paper_session",
        target_id=session.id,
    )
    return session


def run_paper_tick(db: Session, *, user: User, session: PaperSession) -> dict:
    if session.status != "running":
        return {"status": "not_running"}
    version = db.get(StrategyVersion, session.strategy_version_id)
    if version is None:
        raise bad_request("strategy_version_missing", "Session has no strategy version.")
    strategy = db.get(Strategy, version.strategy_id)
    impl = get_strategy(strategy.code) if strategy else None
    if impl is None:
        raise bad_request("strategy_not_found", "Strategy implementation is unavailable.")

    candles, meta = market_data.get_candles(session.instrument_symbol, session.timeframe, 400)
    position = (
        db.query(Position)
        .filter(
            Position.paper_session_id == session.id,
            Position.instrument_symbol == session.instrument_symbol,
            Position.status == "open",
        )
        .first()
    )
    params = (session.config or {}).get("params") or version.default_params or {}
    state = (
        PositionState(side=position.side, quantity=float(position.quantity), entry_price=float(position.avg_entry_price))
        if position
        else None
    )
    signal = impl.generate(candles, params, state)
    snapshot = market_data.get_ticker(session.instrument_symbol)
    actions = []

    if signal.action in ("buy", "sell") and position is None:
        stop = signal.stop_loss
        risk_pct = float(params.get("risk_per_trade_pct", 1.0)) / 100.0
        risk_amount = float(session.equity) * risk_pct
        if stop and abs(snapshot.price - stop) > 0:
            qty = risk_amount / abs(snapshot.price - stop)
        else:
            qty = (float(session.equity) * 0.02) / snapshot.price
        spec = market_data.instrument_spec(session.instrument_symbol) or {}
        step = float(spec.get("step") or 0)
        if step:
            qty = max(step, round(qty / step) * step)
        result = submit_order(
            db,
            user=user,
            request=OrderRequest(
                symbol=session.instrument_symbol,
                side="buy" if signal.action == "buy" else "sell",
                quantity=qty,
                mode="paper",
                paper_session_id=session.id,
                strategy_version_id=version.id,
                stop_loss=stop,
                take_profit=signal.take_profit,
                reason=signal.reason,
            ),
            source="ai_strategy",
        )
        actions.append(
            {
                "action": signal.action,
                "approved": result["decision"].decision == "approved",
                "order_id": result["order"].id,
                "reason": signal.reason,
            }
        )
    elif signal.action == "exit" and position is not None:
        result = close_position(db, user=user, position=position, reason=signal.reason)
        actions.append({"action": "exit", "order_id": result["order"].id, "reason": signal.reason})

    # Refresh marks and equity.
    for pos in db.query(Position).filter(Position.paper_session_id == session.id, Position.status == "open").all():
        mark = market_data.get_ticker(pos.instrument_symbol).price
        pos.mark_price = mark
        pos.unrealized_pnl = (
            (mark - float(pos.avg_entry_price)) * float(pos.quantity)
            if pos.side == "long"
            else (float(pos.avg_entry_price) - mark) * float(pos.quantity)
        )
    open_positions = db.query(Position).filter(Position.paper_session_id == session.id, Position.status == "open").all()
    equity = float(session.cash_balance) + sum(float(p.unrealized_pnl or 0) for p in open_positions)
    session.equity = equity
    session.last_tick_at = _utcnow()
    peak = float((session.config or {}).get("peak_equity") or session.starting_balance)
    session.config = {**(session.config or {}), "peak_equity": max(peak, equity)}
    db.commit()
    return {
        "status": "ok",
        "signal": signal.action,
        "reason": signal.reason,
        "actions": actions,
        "equity": equity,
        "data_source": meta.get("source"),
        "is_demo_feed": bool(meta.get("is_demo")),
        "bars": len(candles),
    }
