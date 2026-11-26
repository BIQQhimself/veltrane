"""Live execution against Deriv, behind the gate and the deterministic risk engine.

Order of operations for every venue-bound contract — none may be skipped:

1. ``execution_gate``: platform switch (real accounts), authorisation, kill switches, permissions.
2. Duplicate guard: identical intent inside the window, or an idempotency key replay.
3. Fresh venue pricing (proposal) and a market snapshot; stale data is rejected.
4. ``risk.binary``: the independent rule set, with terms taken from the venue's own proposal.
5. Only then ``provider.place_order``. A rejected or blocked intent never reaches the adapter.

Everything is persisted: ``Order``, ``RiskDecision``, audit entry, notification. A venue demo
account is flagged ``is_demo`` end to end so no view can present it as real money.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime, timedelta

from app.core.errors import bad_request, conflict, not_found
from app.db.constants import AuditAction, NotificationCategory, Severity
from app.db.models import Balance, Connection, Order, Position, RiskDecision, Trade, User
from app.providers.base import CredentialBundle, ProviderError
from app.providers.deriv import DerivProvider
from app.risk import binary as binary_risk
from app.risk.types import OrderIntent
from app.services import audit, deriv_sessions, execution_gate, market_data, notifications, usage
from app.trading import engine as trading_engine
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

DUPLICATE_WINDOW_SECONDS = 15
STALE_QUOTE_SECONDS = 30


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _provider(db: Session, connection: Connection) -> DerivProvider:
    return deriv_sessions.adapter()


def _credentials(db: Session, connection: Connection) -> CredentialBundle:
    from app.services.connections import load_credentials

    return load_credentials(db, connection)


def _terms(proposal: dict, duration: int, duration_unit: str) -> binary_risk.BinaryTerms:
    stake_min = float(((proposal.get("validation_params") or {}).get("stake") or {}).get("min") or 0.0)
    amount = float(proposal.get("ask_price") or 0.0)
    payout = float(proposal.get("payout") or 0.0)
    payout_pct = round((payout / amount - 1) * 100, 4) if amount else 0.0
    duration_seconds = duration if duration_unit == "s" else duration * 60
    return binary_risk.BinaryTerms(
        duration_seconds=max(1, duration_seconds),
        payout_pct=payout_pct,
        min_stake=stake_min,
        max_stake=1_000_000.0,  # Deriv enforces its own maximum; the platform cap applies too.
        allowed_durations=(duration_seconds,),
    )


VENUE_MARKET_ASSET_CLASS = {
    "synthetic_index": "synthetic",
    "forex": "forex",
    "indices": "index",
    "commodities": "commodity",
    "cryptocurrency": "crypto",
    "stock_indices": "index",
}


def _asset_class(row: dict) -> str:
    return VENUE_MARKET_ASSET_CLASS.get(str(row.get("market") or ""), "synthetic")


def _refresh_balance(db: Session, connection: Connection, provider: DerivProvider) -> None:
    """Read the venue balance before sizing. The risk engine must never size against an unknown equity."""
    try:
        rows = provider.fetch_balances(_credentials(db, connection))
    except ProviderError as exc:
        raise bad_request(
            "balance_unavailable",
            f"Deriv balance could not be read, so no contract was submitted ({exc.message}).",
        ) from exc
    from app.services.connections import scoped_balances

    now = _utcnow()
    db.query(Balance).filter(Balance.connection_id == connection.id).delete()
    for row in scoped_balances(connection, rows):
        db.add(
            Balance(
                org_id=connection.org_id,
                connection_id=connection.id,
                asset=row["asset"][:24],
                free=row.get("free", 0),
                locked=row.get("locked", 0),
                total=row.get("total", 0),
                usd_value=row.get("usd_value", 0),
                as_of=now,
            )
        )
    connection.last_sync_at = now
    db.flush()


def _snapshot(provider: DerivProvider, symbol: str) -> market_data.MarketSnapshot:
    ticker = provider.fetch_ticker(symbol)
    age = max(0.0, time.time() - ticker.ts)
    return market_data.MarketSnapshot(
        symbol=symbol,
        price=ticker.price,
        bid=None,
        ask=None,
        ts=ticker.ts,
        source="deriv",
        is_demo=False,
        age_seconds=age,
        spread_bps=None,
    )


def preview(db: Session, *, user: User, connection: Connection, payload: dict) -> dict:
    """Price a contract without touching the account. Used by the terminal."""
    provider = _provider(db, connection)
    symbol = (payload.get("symbol") or "").strip()
    if not symbol:
        raise bad_request("symbol_required", "Choose an underlying symbol.")
    stake = float(payload.get("stake") or 0)
    duration = int(payload.get("duration") or 5)
    duration_unit = payload.get("duration_unit") or "t"
    gate = execution_gate.evaluate(db, user=user, connection=connection)
    try:
        proposal = provider.proposal(
            CredentialBundle(),
            {
                "symbol": symbol,
                "stake": stake,
                "side": payload.get("side") or "buy",
                "contract_type": payload.get("contract_type"),
                "duration": duration,
                "duration_unit": duration_unit,
                "currency": payload.get("currency") or connection.provider_currency or "USD",
            },
        )
    except ProviderError as exc:
        raise bad_request(exc.code, exc.message) from exc
    return {
        "proposal": proposal,
        "terms": _terms(proposal, duration, duration_unit).as_dict(),
        "gate": gate.as_dict(),
        "scope": gate.scope,
        "is_demo": gate.scope == execution_gate.DEMO,
        "note": (
            "Prices come from Deriv's public proposal gateway. A losing contract pays nothing; "
            "payout is not a guarantee of profit."
        ),
    }


def _duplicate(db: Session, connection: Connection, payload: dict) -> Order | None:
    """A genuinely identical submission inside the window, not every order on the same symbol.

    Two entries on the same underlying with a different stake, contract type or duration are
    distinct orders: the user is entitled to place both, and the risk engine sizes each one.
    Only a repeat of the same terms — a double click, a retried request — is a duplicate.
    """
    since = _utcnow() - timedelta(seconds=DUPLICATE_WINDOW_SECONDS)
    recent = (
        db.query(Order)
        .filter(
            Order.org_id == connection.org_id,
            Order.connection_id == connection.id,
            Order.instrument_symbol == payload["symbol"],
            Order.side == payload["side"],
            Order.created_at >= since,
        )
        .order_by(Order.created_at.desc())
        .all()
    )
    for row in recent:
        meta = row.meta or {}
        if meta.get("contract_type") != payload.get("contract_type"):
            continue
        if meta.get("duration") != payload.get("duration"):
            continue
        if meta.get("duration_unit") != payload.get("duration_unit"):
            continue
        if abs(float(meta.get("stake") or 0.0) - float(payload.get("stake") or 0.0)) > 1e-9:
            continue
        return row
    return None


def open_contract(
    db: Session,
    *,
    user: User,
    connection: Connection,
    payload: dict,
    source: str = "human",
    reason: str = "",
    idempotency_key: str | None = None,
) -> dict:
    symbol = (payload.get("symbol") or "").strip()
    side = (payload.get("side") or "buy").lower()
    contract_type = (payload.get("contract_type") or ("CALL" if side == "buy" else "PUT")).upper()
    stake = float(payload.get("stake") or 0)
    duration = int(payload.get("duration") or 5)
    duration_unit = payload.get("duration_unit") or "t"
    currency = payload.get("currency") or connection.provider_currency or "USD"

    if not symbol:
        raise bad_request("symbol_required", "Choose an underlying symbol.")
    if stake <= 0:
        raise bad_request("invalid_stake", "Stake must be greater than zero.")
    if side not in ("buy", "sell"):
        raise bad_request("invalid_side", "Side must be buy or sell.")

    key = idempotency_key or f"deriv:{connection.id}:{uuid.uuid4().hex}"
    replay = db.query(Order).filter(Order.org_id == user.org_id, Order.idempotency_key == key).first()
    if replay is not None:
        return {"idempotent_replay": True, "order": _order_dict(replay), "risk": _risk_dict(db, replay)}

    gate = execution_gate.evaluate(db, user=user, connection=connection)
    if not gate.allowed:
        audit.record(
            db,
            action=AuditAction.ORDER_REJECTED,
            org_id=user.org_id,
            actor_user_id=user.id,
            actor_email=user.email,
            target_type="connection",
            target_id=connection.id,
            meta={"stage": "execution_gate", "reasons": gate.reasons, "symbol": symbol},
        )
        db.flush()
        raise bad_request("execution_blocked", gate.blocking_message, {"gate": gate.as_dict()})

    is_demo = gate.scope == execution_gate.DEMO
    provider = _provider(db, connection)
    credentials = _credentials(db, connection)

    duplicate = _duplicate(
        db,
        connection,
        {
            "symbol": symbol,
            "side": side,
            "contract_type": contract_type,
            "stake": stake,
            "duration": duration,
            "duration_unit": duration_unit,
        },
    )
    if duplicate is not None:
        raise conflict(
            "duplicate_order",
            "An identical contract was submitted moments ago. Wait for it to settle before retrying.",
            {"order_id": duplicate.id},
        )

    snapshot = _snapshot(provider, symbol)
    if snapshot.age_seconds > STALE_QUOTE_SECONDS:
        raise bad_request(
            "stale_market_data",
            f"Deriv's last tick for {symbol} is {int(snapshot.age_seconds)}s old. Trading is paused on stale data.",
        )

    try:
        proposal = provider.proposal(
            credentials,
            {
                "symbol": symbol,
                "stake": stake,
                "side": side,
                "contract_type": contract_type,
                "duration": duration,
                "duration_unit": duration_unit,
                "currency": currency,
            },
        )
    except ProviderError as exc:
        raise bad_request(exc.code, exc.message) from exc

    terms = _terms(proposal, duration, duration_unit)
    quantity = stake / snapshot.price if snapshot.price else 0.0
    intent = OrderIntent(
        org_id=user.org_id,
        mode="live",
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type="market",
        price=snapshot.price,
        client_order_id=f"drv-{uuid.uuid4().hex[:20]}",
        idempotency_key=key,
        reason=reason or f"{contract_type} {duration}{duration_unit} {symbol}",
        source=source,
    )
    _refresh_balance(db, connection, provider)
    venue_row = deriv_sessions.venue_symbol_map().get(symbol)
    if venue_row is None:
        raise bad_request(
            "venue_session_unknown",
            f"Deriv's symbol catalogue does not currently list {symbol}, so the contract was not submitted.",
        )
    venue_open = bool(venue_row.get("exchange_is_open")) and not bool(venue_row.get("is_trading_suspended"))
    context = trading_engine.build_context(
        db,
        user=user,
        intent=intent,
        connection=connection,
        session=None,
        snapshot=snapshot,
        venue_demo=is_demo,
        venue_instrument={
            "symbol": symbol,
            "asset_class": _asset_class(venue_row),
            "min_qty": 0.0,
            "qty_step": 0.0,
        },
        market_open=venue_open,
    )
    assessment = binary_risk.evaluate(intent, context, terms)

    decision = RiskDecision(
        org_id=user.org_id,
        order_intent={
            **intent.as_dict(),
            "instrument_type": "binary",
            "contract_type": contract_type,
            "proposal_id": proposal.get("id"),
            **terms.as_dict(),
        },
        decision="approved" if assessment.approved else "rejected",
        failed_rules=[f.as_dict() for f in assessment.failed],
        checks=[c.as_dict() for c in assessment.checks],
        policy_id=assessment.policy_id,
        policy_version=assessment.policy_version,
        correlation_id=f"deriv:{uuid.uuid4().hex}",
    )
    db.add(decision)
    db.flush()

    order = Order(
        org_id=user.org_id,
        mode="live",
        connection_id=connection.id,
        instrument_symbol=symbol,
        side=side,
        order_type="market",
        quantity=quantity,
        price=snapshot.price,
        status="rejected" if not assessment.approved else "submitted",
        client_order_id=intent.client_order_id,
        idempotency_key=key,
        risk_decision_id=decision.id,
        correlation_id=decision.correlation_id,
        rejection_reason=None if assessment.approved else "; ".join(f.message for f in assessment.failed),
        submitted_at=_utcnow(),
        is_demo=is_demo,
        fee_currency=currency,
    )
    db.add(order)
    db.flush()

    audit.record(
        db,
        action=AuditAction.ORDER_INTENT,
        org_id=user.org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        target_type="order",
        target_id=order.id,
        meta={
            "provider": "deriv",
            "connection_id": connection.id,
            "symbol": symbol,
            "contract_type": contract_type,
            "stake": stake,
            "duration": duration,
            "duration_unit": duration_unit,
            "is_demo": is_demo,
            "source": source,
            "gate_checks": [c["check"] for c in gate.checks],
        },
    )

    if not assessment.approved:
        audit.record(
            db,
            action=AuditAction.ORDER_REJECTED,
            org_id=user.org_id,
            target_type="order",
            target_id=order.id,
            meta={"failed_rules": [f.code for f in assessment.failed]},
        )
        notifications.notify(
            db,
            org_id=user.org_id,
            category=NotificationCategory.TRADE,
            severity=Severity.WARNING,
            title="Order rejected by the risk engine",
            body="; ".join(f.message for f in assessment.failed) or "Risk checks failed.",
            data={"order_id": order.id, "connection_id": connection.id},
        )
        db.flush()
        return {
            "approved": False,
            "order": _order_dict(order),
            "risk": _risk_dict(db, order),
            "message": "The risk engine rejected this contract. Nothing was sent to Deriv.",
        }

    try:
        session = deriv_sessions.session_for(db, connection, allowed=True)
        result = provider.place_order(
            credentials,
            {
                "symbol": symbol,
                "side": side,
                "contract_type": contract_type,
                "stake": stake,
                "duration": duration,
                "duration_unit": duration_unit,
                "currency": currency,
            },
            session=session,
            live_authorised=not is_demo,
        )
    except ProviderError as exc:
        order.status = "failed"
        order.rejection_reason = exc.message[:1000]
        deriv_sessions.record_auth_event(
            db,
            connection=connection,
            org_id=connection.org_id,
            event="order_failed",
            outcome="failed",
            code=exc.code,
            message=exc.message,
            detail={"symbol": symbol, "order_id": order.id},
        )
        notifications.notify(
            db,
            org_id=user.org_id,
            category=NotificationCategory.TRADE,
            severity=Severity.CRITICAL,
            title=f"Deriv order failed: {symbol}",
            body=f"{exc.message} No position was opened.",
            data={"order_id": order.id, "connection_id": connection.id},
        )
        db.flush()
        raise bad_request(exc.code, exc.message, {"order_id": order.id}) from exc

    order.status = "filled"
    order.filled_at = _utcnow()
    if is_demo:
        # Demo executions are metered so a free account cannot run the strategy engine for free.
        usage.increment_usage(db, user.org_id, "demo_executions", 1, meta={"order_id": order.id, "provider": "deriv"})
    order.filled_qty = result.get("filled_qty") or 0
    # A fixed-odds contract has no traded price: the stake is the cost and the payout is the
    # terminal value, so the reference price stored on the order is the underlying spot.
    order.avg_fill_price = snapshot.price
    order.fee = float(result.get("fee") or 0)
    order.fee_currency = result.get("fee_currency") or currency
    order.provider_order_id = result.get("provider_order_id")
    order.slippage_est_bps = 0.0
    order.slippage_actual_bps = 0.0

    position = Position(
        org_id=user.org_id,
        mode="live",
        connection_id=connection.id,
        instrument_symbol=symbol,
        side="long" if contract_type.startswith(("CALL", "MULTUP", "HIGHER")) else "short",
        # The maximum loss on a fixed-odds contract is the stake, so exposure is the stake.
        # Carrying quantity=1 would report the underlying price as exposure and exhaust the
        # account limit after a couple of trades.
        quantity=quantity,
        avg_entry_price=snapshot.price,
        mark_price=snapshot.price,
        unrealized_pnl=0.0,
        leverage=1.0,
        status="open",
        opened_at=_utcnow(),
    )
    db.add(position)
    db.flush()
    order.meta = {
        "contract_id": result.get("provider_order_id"),
        "proposal_id": result.get("proposal_id"),
        "payout": result.get("payout"),
        "longcode": result.get("longcode"),
        "contract_type": result.get("contract_type") or contract_type,
        "duration": duration,
        "duration_unit": duration_unit,
        "stake": stake,
        "account_id": connection.provider_account_id,
        "account_type": connection.provider_account_type,
        "position_id": position.id,
        "is_demo": is_demo,
        "quote": {"price": snapshot.price, "ts": snapshot.ts, "source": snapshot.source},
        "costs": {
            "commission": 0.0,
            "note": "Deriv fixed-odds pricing embeds its margin in the payout; there is no separate commission line.",
            "payout": result.get("payout"),
        },
    }

    audit.record(
        db,
        action=AuditAction.ORDER_FILLED,
        org_id=user.org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        target_type="order",
        target_id=order.id,
        meta={
            "provider": "deriv",
            "provider_order_id": order.provider_order_id,
            "is_demo": is_demo,
            "stake": stake,
            "symbol": symbol,
        },
    )
    notifications.notify(
        db,
        org_id=user.org_id,
        category=NotificationCategory.TRADE,
        severity=Severity.INFO,
        title=(f"{'Demo' if is_demo else 'Live'} contract opened: {contract_type} {symbol}"),
        body=(
            f"Stake {stake:.2f} {currency}, duration {duration}{duration_unit}. "
            f"Contract {order.provider_order_id}. "
            + ("Deriv demo account: no real funds at risk." if is_demo else "Real money.")
        ),
        data={"order_id": order.id, "connection_id": connection.id},
    )
    db.flush()
    return {
        "approved": True,
        "order": _order_dict(order),
        "risk": _risk_dict(db, order),
        "venue": {
            "contract_id": order.provider_order_id,
            "payout": result.get("payout"),
            "balance_after": result.get("balance_after"),
            "is_demo": is_demo,
        },
    }


def record_settlement(
    db: Session,
    *,
    order: Order,
    position: Position | None,
    realized: float,
    exit_price: float,
    reason: str,
    contract: dict | None = None,
    human_intervention: bool = False,
    intervention_note: str | None = None,
) -> Trade | None:
    """Write the immutable trade record for a settled venue contract.

    Deriv reports ``profit`` on a closed contract already net of everything the venue charges,
    so it is both the gross and net figure; the payout margin is noted in the snapshot instead of
    being deducted twice. Idempotent: a contract that reconciles twice keeps one trade row.
    """
    existing = db.query(Trade).filter(Trade.order_id == order.id).first()
    if existing is not None:
        return existing
    meta = order.meta or {}
    now = _utcnow()
    entry_price = float((meta.get("quote") or {}).get("price") or order.avg_fill_price or 0.0)
    stake = float(meta.get("stake") or order.quantity or 0.0)
    trade = Trade(
        org_id=order.org_id,
        order_id=order.id,
        position_id=position.id if position is not None else meta.get("position_id"),
        mode=order.mode,
        instrument_symbol=order.instrument_symbol,
        side=order.side,
        quantity=stake,
        entry_price=entry_price,
        exit_price=exit_price,
        notional=stake,
        fees=0.0,
        funding=0.0,
        slippage_est_bps=0.0,
        slippage_actual_bps=0.0,
        gross_pnl=realized,
        net_pnl=realized,
        entry_reason=(
            f"Deriv {meta.get('contract_type') or order.side} contract placed from the trading "
            f"terminal, stake {stake:.2f} {order.fee_currency}."
        ),
        exit_reason=reason,
        strategy_version_id=order.strategy_version_id,
        risk_snapshot={
            "provider": "deriv",
            "contract_id": order.provider_order_id,
            "contract_type": meta.get("contract_type"),
            "duration": meta.get("duration"),
            "duration_unit": meta.get("duration_unit"),
            "stake": stake,
            "payout": meta.get("payout"),
            "sold_for": meta.get("sold_for"),
            "account_id": meta.get("account_id"),
            "account_type": meta.get("account_type"),
            "cost_note": (
                "Venue profit is net of Deriv's embedded fixed-odds margin; there is no separate commission line."
            ),
            "settlement": contract or {},
        },
        is_demo=order.is_demo,
        human_intervention=human_intervention,
        intervention_note=intervention_note,
        opened_at=order.filled_at or order.submitted_at or now,
        closed_at=now,
    )
    db.add(trade)
    db.flush()
    return trade


def close_contract(
    db: Session,
    *,
    user: User,
    connection: Connection,
    contract_id: str,
    reason: str = "deriv_early_exit",
    intervention_note: str = "Closed early by the account owner from the trading terminal.",
) -> dict:
    gate = execution_gate.evaluate(db, user=user, connection=connection)
    if not gate.allowed:
        raise bad_request("execution_blocked", gate.blocking_message, {"gate": gate.as_dict()})

    provider = _provider(db, connection)
    credentials = _credentials(db, connection)
    session = deriv_sessions.session_for(db, connection, allowed=True)
    try:
        result = provider.cancel_order(credentials, contract_id, session=session)
    except ProviderError as exc:
        raise bad_request(exc.code, exc.message) from exc

    order = (
        db.query(Order)
        .filter(
            Order.org_id == user.org_id,
            Order.connection_id == connection.id,
            Order.provider_order_id == str(contract_id),
        )
        .first()
    )
    stake = float((order.meta or {}).get("stake") or 0) if order is not None else 0.0
    sold_for = float(result.get("sold_for") or 0)
    realized = round(sold_for - stake, 8) if order is not None else 0.0
    if order is not None:
        order.status = "closed"
        order.meta = {
            **(order.meta or {}),
            "sold_for": result.get("sold_for"),
            "realized_pnl": realized,
            "closed_at": _utcnow().isoformat(),
        }
        position = (
            db.get(Position, (order.meta or {}).get("position_id")) if (order.meta or {}).get("position_id") else None
        )
        if position is not None and position.status == "open":
            # An early exit realises P&L now; waiting for reconciliation would leave a closed
            # contract showing as an open position with no settled result.
            position.status = "closed"
            position.unrealized_pnl = realized
            position.realized_pnl = realized
            position.closed_at = _utcnow()
        record_settlement(
            db,
            order=order,
            position=position,
            realized=realized,
            exit_price=sold_for,
            reason=reason,
            contract=result,
            human_intervention=intervention_note != "",
            intervention_note=intervention_note,
        )
    audit.record(
        db,
        action=AuditAction.ORDER_CANCELLED,
        org_id=user.org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        target_type="order",
        target_id=order.id if order else connection.id,
        meta={
            "provider": "deriv",
            "contract_id": contract_id,
            "sold_for": result.get("sold_for"),
            "stake": stake,
            "realized_pnl": realized,
        },
    )
    notifications.notify(
        db,
        org_id=user.org_id,
        category=NotificationCategory.TRADE,
        severity=Severity.INFO,
        title=f"Contract closed early: {contract_id}",
        body=(
            f"Sold for {sold_for:.2f} against a {stake:.2f} stake "
            f"({'+' if realized >= 0 else ''}{realized:.2f} realised, venue early exit)."
        ),
        data={"order_id": order.id if order else None},
    )
    db.flush()
    return result


def sync_positions(db: Session, *, connection: Connection) -> dict:
    """Reconcile the venue's open contracts against the platform's ledger.

    Contracts are tracked by contract id, not by symbol: a user can hold two contracts on the
    same index. A contract that has left the venue's portfolio has expired, so its settlement is
    read from the venue and written as an immutable trade; the previous behaviour copied the last
    unrealised mark into realised P&L, which reported a guess as a settled result.
    """
    provider = _provider(db, connection)
    credentials = _credentials(db, connection)
    try:
        contracts = provider.open_contracts(credentials)
    except ProviderError as exc:
        raise bad_request(exc.code, exc.message) from exc

    open_orders = (
        db.query(Order)
        .filter(
            Order.connection_id == connection.id,
            Order.provider_order_id.isnot(None),
            Order.status.in_(("filled", "partially_filled", "pending")),
        )
        .all()
    )
    by_id = {str(c.get("contract_id")): c for c in contracts}
    settled = 0
    for order in open_orders:
        contract = by_id.get(str(order.provider_order_id))
        position = (
            db.get(Position, (order.meta or {}).get("position_id")) if (order.meta or {}).get("position_id") else None
        )
        if contract is not None:
            if position is not None and position.status == "open":
                position.mark_price = float(contract.get("current_spot") or position.mark_price)
                position.unrealized_pnl = float(contract.get("profit") or 0)
            continue
        try:
            detail = provider.contract_status(credentials, str(order.provider_order_id))
        except ProviderError as exc:
            log.warning(
                "deriv_settle_lookup_failed",
                extra={"contract_id": order.provider_order_id, "error": exc.message},
            )
            continue
        if not detail or not detail.get("is_sold"):
            # Still open at the venue but missing from the portfolio snapshot: leave the ledger
            # alone and retry on the next sync rather than inventing a result.
            continue
        realized = float(detail.get("profit") or 0)
        exit_price = float(detail.get("sell_price") or detail.get("exit_tick") or 0)
        order.status = "closed"
        order.meta = {
            **(order.meta or {}),
            "sold_for": detail.get("sell_price"),
            "realized_pnl": realized,
            "closed_at": _utcnow().isoformat(),
            "settlement_status": detail.get("status"),
        }
        if position is not None and position.status == "open":
            position.status = "closed"
            position.unrealized_pnl = realized
            position.realized_pnl = realized
            position.closed_at = _utcnow()
        record_settlement(
            db,
            order=order,
            position=position,
            realized=realized,
            exit_price=exit_price,
            reason=f"deriv_settlement:{detail.get('status') or 'sold'}",
            contract=detail,
        )
        settled += 1
    db.flush()
    return {
        "open_contracts": len(contracts),
        "settled": settled,
        "reconciled_at": _utcnow().isoformat(),
    }


# ---------------------------------------------------------------------- serialisation
def _order_dict(order: Order) -> dict:
    return {
        "id": order.id,
        "status": order.status,
        "symbol": order.instrument_symbol,
        "side": order.side,
        "quantity": float(order.quantity),
        "price": float(order.price) if order.price is not None else None,
        "filled_qty": float(order.filled_qty or 0),
        "avg_fill_price": float(order.avg_fill_price) if order.avg_fill_price is not None else None,
        "fee": float(order.fee or 0),
        "fee_currency": order.fee_currency,
        "provider_order_id": order.provider_order_id,
        "is_demo": order.is_demo,
        "mode": order.mode,
        "connection_id": order.connection_id,
        "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
        "filled_at": order.filled_at.isoformat() if order.filled_at else None,
        "rejection_reason": order.rejection_reason,
        "meta": order.meta or {},
    }


def _risk_dict(db: Session, order: Order) -> dict | None:
    if not order.risk_decision_id:
        return None
    decision = db.get(RiskDecision, order.risk_decision_id)
    if decision is None:
        return None
    return {
        "id": decision.id,
        "decision": decision.decision,
        "failed_rules": decision.failed_rules,
        "checks": decision.checks,
        "policy_version": decision.policy_version,
    }


def trade_detail(db: Session, *, org_id: str, order_id: str) -> dict:
    order = db.get(Order, order_id)
    if order is None or order.org_id != org_id:
        raise not_found("order_not_found", "Order not found.")
    return {"order": _order_dict(order), "risk": _risk_dict(db, order)}
