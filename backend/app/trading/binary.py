"""Fixed-odds binary contracts: quotes, opening, settlement.

Honesty rules enforced here:

* Contracts are paper only. There is no live binary route in this build, and the
  code refuses anything but ``paper`` mode rather than implying venue support.
* Prices come from the market-data service, which labels demo series as demo.
  The contract row stores ``price_source`` and ``is_demo`` so no downstream view
  can present a simulated settlement as real.
* Every contract passes the independent risk engine. A rejected contract is
  persisted for audit with the failing checks, exactly like a rejected order.
* The stake is debited at open and the payout credited at settlement, so the
  paper cash balance always reflects committed capital.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.errors import bad_request, not_found
from app.db.constants import AuditAction, NotificationCategory, Severity
from app.db.models import BinaryContract, PaperSession, RiskDecision, Trade, User
from app.risk import binary as binary_risk
from app.risk.types import OrderIntent
from app.services import audit, market_data, notifications, usage
from app.trading import engine as trading_engine
from sqlalchemy.orm import Session

ALLOWED_DURATIONS: tuple[int, ...] = (60, 300, 900, 1800, 3600)

# Platform modelling parameters for a simulated fixed-odds book. They are not a
# promise of return: the payout is what a winning contract would pay, and a losing
# contract pays nothing. Persisted per contract for auditability.
PAYOUT_TABLE: dict[str, dict[int, float]] = {
    "crypto": {60: 78, 300: 80, 900: 82, 1800: 84, 3600: 86},
    "forex": {60: 72, 300: 74, 900: 76, 1800: 78, 3600: 80},
    "stock": {60: 70, 300: 73, 900: 75, 1800: 77, 3600: 79},
    "commodity": {60: 71, 300: 74, 900: 76, 1800: 78, 3600: 80},
}

# Indices are deliberately excluded from the user-facing binary universe.
EXCLUDED_ASSET_CLASSES = {"index"}

ASSET_LABELS = {
    "BTC/USDT": "Bitcoin",
    "ETH/USDT": "Ethereum",
    "SOL/USDT": "Solana",
    "BNB/USDT": "BNB",
    "XRP/USDT": "XRP",
    "ADA/USDT": "Cardano",
    "EUR/USD": "Euro / US Dollar",
    "GBP/USD": "British Pound / US Dollar",
    "USD/JPY": "US Dollar / Japanese Yen",
    "XAU/USD": "Gold",
    "AAPL/USD": "Apple",
    "NVDA/USD": "NVIDIA",
    "TSLA/USD": "Tesla",
    "MSFT/USD": "Microsoft",
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _payout(symbol: str, duration_seconds: int) -> float:
    spec = market_data.instrument_spec(symbol) or {}
    asset_class = spec.get("asset_class", "crypto")
    table = PAYOUT_TABLE.get(asset_class, PAYOUT_TABLE["crypto"])
    return float(table.get(duration_seconds, 75))


def asset_universe() -> list[dict]:
    rows = []
    for row in market_data.supported_symbols():
        if row["asset_class"] in EXCLUDED_ASSET_CLASSES:
            continue
        payouts = {str(d): _payout(row["symbol"], d) for d in ALLOWED_DURATIONS}
        rows.append(
            {
                **row,
                "name": ASSET_LABELS.get(row["symbol"], row["symbol"]),
                "payouts": payouts,
                "durations": list(ALLOWED_DURATIONS),
                "min_stake": settings.binary_min_stake,
                "max_stake": settings.binary_max_stake,
                "binary_enabled": True,
                "is_demo": row.get("data_source") == "demo",
            }
        )
    rows.sort(key=lambda r: (r["asset_class"], r["symbol"]))
    return rows


def quote(symbol: str, duration_seconds: int) -> dict:
    if symbol not in {r["symbol"] for r in asset_universe()}:
        raise not_found("instrument_not_found", "This asset is not offered for binary contracts.")
    if duration_seconds not in ALLOWED_DURATIONS:
        raise bad_request("invalid_duration", f"Duration must be one of {list(ALLOWED_DURATIONS)} seconds.")
    snapshot = market_data.get_ticker(symbol)
    now = _utcnow()
    spec = market_data.instrument_spec(symbol) or {}
    return {
        "symbol": symbol,
        "name": ASSET_LABELS.get(symbol, symbol),
        "asset_class": spec.get("asset_class"),
        "price": snapshot.price,
        "bid": snapshot.bid,
        "ask": snapshot.ask,
        "payout_pct": _payout(symbol, duration_seconds),
        "duration_seconds": duration_seconds,
        "expires_at": (now + timedelta(seconds=duration_seconds)).isoformat(),
        "min_stake": settings.binary_min_stake,
        "max_stake": settings.binary_max_stake,
        "price_source": snapshot.source,
        "is_demo": snapshot.is_demo,
        "price_age_seconds": snapshot.age_seconds,
        "quoted_at": now.isoformat(),
        "disclaimer": (
            "Simulated fixed-odds contract on simulated prices. A losing contract pays nothing; "
            "payout is not a guarantee of profit."
        ),
    }


def open_contract(
    db: Session,
    *,
    user: User,
    symbol: str,
    direction: str,
    stake: float,
    duration_seconds: int,
    source: str = "human",
    reason: str = "",
    idempotency_key: str | None = None,
) -> dict:
    direction = (direction or "").lower()
    if direction not in ("call", "put"):
        raise bad_request("invalid_direction", "Direction must be call or put.")
    if stake <= 0:
        raise bad_request("invalid_stake", "Stake must be positive.")
    universe = {r["symbol"]: r for r in asset_universe()}
    if symbol not in universe:
        raise not_found("instrument_not_found", "This asset is not offered for binary contracts.")
    if duration_seconds not in ALLOWED_DURATIONS:
        raise bad_request("invalid_duration", f"Duration must be one of {list(ALLOWED_DURATIONS)} seconds.")

    key = idempotency_key or f"bin:{user.org_id}:{uuid.uuid4().hex}"
    existing = (
        db.query(BinaryContract)
        .filter(BinaryContract.org_id == user.org_id, BinaryContract.idempotency_key == key)
        .first()
    )
    if existing is not None:
        decision = db.get(RiskDecision, existing.risk_decision_id) if existing.risk_decision_id else None
        return {"idempotent_replay": True, "contract": existing, "decision": decision, "trade": None}

    session: PaperSession = trading_engine.paper_session_for(db, user, None)
    snapshot = market_data.get_ticker(symbol)
    payout = _payout(symbol, duration_seconds)
    terms = binary_risk.BinaryTerms(
        duration_seconds=duration_seconds,
        payout_pct=payout,
        min_stake=settings.binary_min_stake,
        max_stake=settings.binary_max_stake,
        allowed_durations=ALLOWED_DURATIONS,
    )

    # quantity = stake / price so the shared notional rules measure committed capital.
    quantity = stake / snapshot.price if snapshot.price else 0.0
    intent = OrderIntent(
        org_id=user.org_id,
        mode="paper",
        symbol=symbol,
        side="buy",
        quantity=quantity,
        order_type="market",
        client_order_id=f"bin-{uuid.uuid4().hex[:20]}",
        idempotency_key=key,
        reason=reason or f"{direction.upper()} {duration_seconds}s binary contract",
        source=source,
    )
    context = trading_engine.build_context(
        db, user=user, intent=intent, connection=None, session=session, snapshot=snapshot
    )
    assessment = binary_risk.evaluate(intent, context, terms)

    now = _utcnow()
    contract = BinaryContract(
        org_id=user.org_id,
        user_id=user.id,
        paper_session_id=session.id,
        mode="paper",
        instrument_symbol=symbol,
        asset_class=universe[symbol]["asset_class"],
        direction=direction,
        stake=round(stake, 2),
        payout_pct=payout,
        duration_seconds=duration_seconds,
        entry_price=snapshot.price,
        price_source=snapshot.source,
        is_demo=True,
        status="open" if assessment.approved else "rejected",
        opened_at=now,
        expires_at=now + timedelta(seconds=duration_seconds),
        source=source,
        entry_reason=intent.reason,
        rejection_reason=None if assessment.approved else "; ".join(f.message for f in assessment.failed),
        risk_snapshot={
            "terms": terms.as_dict(),
            "checks_passed": [c.code for c in assessment.checks if c.passed],
            "checks_failed": [c.code for c in assessment.checks if not c.passed],
            "price_source": snapshot.source,
            "is_demo": True,
        },
        idempotency_key=key,
    )
    db.add(contract)
    db.flush()

    decision = RiskDecision(
        org_id=user.org_id,
        order_intent={**intent.as_dict(), "instrument_type": "binary", **terms.as_dict()},
        decision="approved" if assessment.approved else "rejected",
        failed_rules=[f.as_dict() for f in assessment.failed],
        checks=[c.as_dict() for c in assessment.checks],
        policy_id=assessment.policy_id,
        policy_version=assessment.policy_version,
        correlation_id=f"binary:{contract.id}",
    )
    db.add(decision)
    db.flush()
    contract.risk_decision_id = decision.id

    audit.record(
        db,
        action=AuditAction.ORDER_INTENT,
        org_id=user.org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        target_type="binary_contract",
        target_id=contract.id,
        meta={
            "symbol": symbol,
            "direction": direction,
            "stake": contract.stake,
            "duration_seconds": duration_seconds,
            "payout_pct": payout,
            "source": source,
            "is_demo": True,
        },
    )

    if not assessment.approved:
        audit.record(
            db,
            action=AuditAction.ORDER_REJECTED,
            org_id=user.org_id,
            actor_user_id=user.id,
            target_type="binary_contract",
            target_id=contract.id,
            meta={"failed_rules": assessment.failed_codes, "instrument_type": "binary"},
        )
        notifications.notify(
            db,
            org_id=user.org_id,
            category=NotificationCategory.ORDER,
            severity=Severity.WARNING,
            title=f"Contract rejected: {symbol} {direction.upper()}",
            body=contract.rejection_reason or "The risk engine rejected this contract.",
            data={"binary_contract_id": contract.id, "failed_rules": assessment.failed_codes},
        )
        db.commit()
        return {"idempotent_replay": False, "contract": contract, "decision": decision, "trade": None}

    # Commit the stake: cash moves out of the paper balance for the contract term.
    session.cash_balance = float(session.cash_balance) - contract.stake
    session.equity = float(session.cash_balance) + _open_stake_total(db, user.org_id)
    usage.increment_usage(db, user.org_id, "demo_executions", 1, meta={"binary_contract_id": contract.id})
    notifications.notify(
        db,
        org_id=user.org_id,
        category=NotificationCategory.ORDER,
        severity=Severity.INFO,
        title=f"Simulated contract open: {symbol} {direction.upper()}",
        body=(
            f"{contract.stake:.2f} staked for {duration_seconds}s at {payout:.0f}% payout. "
            f"Expires {contract.expires_at.isoformat()}. Paper execution — no real funds moved."
        ),
        data={"binary_contract_id": contract.id, "is_demo": True},
    )
    audit.record(
        db,
        action=AuditAction.ORDER_FILLED,
        org_id=user.org_id,
        actor_user_id=user.id,
        target_type="binary_contract",
        target_id=contract.id,
        meta={"entry_price": contract.entry_price, "stake": contract.stake, "is_demo": True},
    )
    db.commit()
    return {"idempotent_replay": False, "contract": contract, "decision": decision, "trade": None}


def _open_stake_total(db: Session, org_id: str) -> float:
    rows = (
        db.query(BinaryContract.stake)
        .filter(BinaryContract.org_id == org_id, BinaryContract.status == "open")
        .all()
    )
    return float(sum(float(r[0]) for r in rows))


def settle_due(db: Session, *, org_id: str) -> list[BinaryContract]:
    """Settle every expired open contract for the organisation.

    Called lazily from read endpoints so settlement happens even when no worker is
    running. Each settlement writes a Trade row so history, portfolio and analytics
    treat binaries like any other closed position.
    """
    now = _utcnow()
    due = (
        db.query(BinaryContract)
        .filter(
            BinaryContract.org_id == org_id,
            BinaryContract.status == "open",
            BinaryContract.expires_at <= now,
        )
        .order_by(BinaryContract.expires_at.asc())
        .limit(50)
        .all()
    )
    settled: list[BinaryContract] = []
    for contract in due:
        snapshot = market_data.get_ticker(contract.instrument_symbol)
        exit_price = float(snapshot.price)
        entry_price = float(contract.entry_price)
        if abs(exit_price - entry_price) < 1e-12:
            status = "void"
            net = 0.0
            credit = float(contract.stake)
        else:
            won = exit_price > entry_price if contract.direction == "call" else exit_price < entry_price
            status = "won" if won else "lost"
            if won:
                net = round(float(contract.stake) * float(contract.payout_pct) / 100.0, 2)
                credit = float(contract.stake) + net
            else:
                net = -float(contract.stake)
                credit = 0.0

        contract.status = status
        contract.exit_price = exit_price
        contract.settled_at = now
        contract.net_pnl = net

        session = db.get(PaperSession, contract.paper_session_id) if contract.paper_session_id else None
        if session is not None:
            session.cash_balance = float(session.cash_balance) + credit
            session.equity = float(session.cash_balance) + _open_stake_total(db, org_id)

        db.add(
            Trade(
                org_id=contract.org_id,
                order_id=None,
                position_id=None,
                paper_session_id=contract.paper_session_id,
                mode="paper",
                instrument_symbol=contract.instrument_symbol,
                side="long" if contract.direction == "call" else "short",
                quantity=float(contract.stake),
                entry_price=entry_price,
                exit_price=exit_price,
                notional=float(contract.stake),
                fees=0.0,
                funding=0.0,
                slippage_est_bps=0.0,
                slippage_actual_bps=0.0,
                gross_pnl=net,
                net_pnl=net,
                entry_reason=contract.entry_reason,
                exit_reason=f"binary_expiry:{status}",
                risk_snapshot={
                    "instrument_type": "binary",
                    "direction": contract.direction,
                    "stake": float(contract.stake),
                    "payout_pct": float(contract.payout_pct),
                    "duration_seconds": contract.duration_seconds,
                    "expiry_price": exit_price,
                    "price_source": contract.price_source,
                    "is_demo": True,
                },
                is_demo=True,
                opened_at=contract.opened_at,
                closed_at=now,
            )
        )
        audit.record(
            db,
            action=AuditAction.TRADE_CLOSED,
            org_id=contract.org_id,
            target_type="binary_contract",
            target_id=contract.id,
            meta={
                "status": status,
                "net_pnl": net,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "is_demo": True,
            },
        )
        notifications.notify(
            db,
            org_id=contract.org_id,
            category=NotificationCategory.TRADE,
            severity=Severity.SUCCESS if net > 0 else (Severity.INFO if net == 0 else Severity.WARNING),
            title=f"Simulated contract settled: {contract.instrument_symbol} {contract.direction.upper()}",
            body=(
                f"{status.upper()} at {exit_price} (entry {entry_price}). "
                f"Net {net:+.2f} USD after costs. Paper settlement only."
            ),
            data={"binary_contract_id": contract.id, "is_demo": True},
        )
        settled.append(contract)
    if settled:
        db.commit()
    return settled


def list_contracts(db: Session, *, org_id: str, status: str | None = None, limit: int = 100) -> list[BinaryContract]:
    query = db.query(BinaryContract).filter(BinaryContract.org_id == org_id)
    if status in ("open", "won", "lost", "void", "rejected"):
        query = query.filter(BinaryContract.status == status)
    return query.order_by(BinaryContract.opened_at.desc()).limit(min(limit, 300)).all()


def summary(db: Session, *, org_id: str) -> dict:
    rows = db.query(BinaryContract).filter(BinaryContract.org_id == org_id).all()
    settled = [c for c in rows if c.status in ("won", "lost", "void")]
    wins = [c for c in settled if c.status == "won"]
    losses = [c for c in settled if c.status == "lost"]
    net = sum(float(c.net_pnl) for c in settled)
    staked = sum(float(c.stake) for c in settled)
    open_rows = [c for c in rows if c.status == "open"]
    return {
        "contracts": len(rows),
        "open": len(open_rows),
        "open_stake": round(sum(float(c.stake) for c in open_rows), 2),
        "settled": len(settled),
        "wins": len(wins),
        "losses": len(losses),
        "voids": len([c for c in settled if c.status == "void"]),
        "win_rate_pct": round(len(wins) / len(settled) * 100, 2) if settled else None,
        "net_pnl": round(net, 2),
        "staked_total": round(staked, 2),
        "return_on_stake_pct": round(net / staked * 100, 2) if staked else None,
        "avg_payout_pct": round(sum(float(c.payout_pct) for c in rows) / len(rows), 2) if rows else None,
        "is_demo": True,
        "note": "All figures come from simulated contracts settled on simulated prices.",
    }
