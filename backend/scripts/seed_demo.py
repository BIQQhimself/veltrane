"""Provision the shareable demo account. Idempotent; safe to run repeatedly.

Usage:
    VELTRANE_DEMO_EMAIL=demo@veltrane.ai VELTRANE_DEMO_PASSWORD='...' \
        python -m scripts.seed_demo

What it creates:
  * one non-staff account in its own organization, email already verified
  * a Pro subscription granted through the normal billing activation path, with the
    payment recorded under the "demo" provider so it is never mistaken for revenue
  * a running paper session on a system strategy
  * settled fixed-odds contracts and one open CFD position, produced by the real
    engines so every figure reconciles with the trade ledger

Everything it writes is simulated. The account cannot reach live trading: the
platform-wide flag stays off and live authorization is a separate user action.
"""
from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import BinaryContract, Organization, Position, User
from app.db.session import SessionLocal
from app.services import auth, billing, strategy_service
from app.trading import binary as binary_engine
from scripts.seed import seed

DEMO_EMAIL = os.environ.get("VELTRANE_DEMO_EMAIL", "demo@veltrane.ai")
DEMO_PASSWORD = os.environ.get("VELTRANE_DEMO_PASSWORD", "Veltrane!Demo2026")
DEMO_NAME = "Avery Chen"

# Instruments and durations cycled through the backfilled history.
DEMO_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XAU/USD", "EUR/USD", "AAPL/USD"]
DEMO_DURATIONS = [300, 900, 1800]
HISTORY_COUNT = 42


def _demo_user(db) -> User:
    user = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if user is not None:
        return user

    org = Organization(
        name="VELTRANE Demo",
        slug=f"veltrane-demo-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        timezone="UTC",
    )
    db.add(org)
    db.flush()
    user = User(
        org_id=org.id,
        email=DEMO_EMAIL,
        password_hash=auth.hash_password(DEMO_PASSWORD),
        full_name=DEMO_NAME,
        status="active",
        email_verified_at=datetime.now(UTC),
        is_staff=False,
        staff_role=None,
        terms_accepted_at=datetime.now(UTC),
        terms_version="terms-2026-01",
    )
    db.add(user)
    db.flush()
    billing.ensure_free_subscription(db, org.id)
    db.commit()
    return user


def _grant_pro(db, user: User) -> None:
    sub = billing.ensure_free_subscription(db, user.org_id)
    if sub.plan_code == "pro" and sub.status in ("active", "trialing"):
        return
    billing.activate_plan(
        db,
        org_id=user.org_id,
        plan_code="pro",
        provider="demo",
        provider_subscription_id=f"demo_{user.org_id}",
        amount=49.0,
        event_id=f"demo-grant-{user.org_id}",
        trial=False,
    )
    db.commit()


def _ensure_session(db, user: User) -> None:
    from app.db.models import PaperSession

    running = (
        db.query(PaperSession)
        .filter(PaperSession.org_id == user.org_id, PaperSession.status == "running")
        .count()
    )
    if running:
        return
    strategy_service.start_paper_session(
        db,
        user=user,
        code="trend_following_v1",
        symbol="BTC/USDT",
        timeframe="1h",
    )
    db.commit()


def _ensure_contracts(db, user: User) -> None:
    """Backfill closed contracts on historical demo candles.

    Each row is priced the way the live engine would have priced it: entry at the
    bar containing the open time, exit at the bar containing expiry, direction from
    a fixed momentum rule on the preceding minute, and the documented settlement
    rule applied to the result. Nothing is invented - the prices come from the demo
    feed and the outcomes follow from them, which is why the win rate is unflattering.
    """
    from app.db.models import PaperSession, Trade
    from app.services import market_data
    from app.trading.binary import asset_universe

    if db.query(BinaryContract).filter(BinaryContract.org_id == user.org_id).count():
        return

    universe = {row["symbol"]: row for row in asset_universe()}
    session = (
        db.query(PaperSession)
        .filter(PaperSession.org_id == user.org_id)
        .order_by(PaperSession.created_at.desc())
        .first()
    )
    now = datetime.now(UTC)
    cash = float(session.cash_balance) if session else settings.paper_starting_balance

    for index in range(HISTORY_COUNT):
        symbol = DEMO_SYMBOLS[index % len(DEMO_SYMBOLS)]
        duration = DEMO_DURATIONS[index % len(DEMO_DURATIONS)]
        # Six hours apart over the last ten days, so the equity curve and the
        # daily analytics have a real shape rather than two points.
        opened_at = now - timedelta(minutes=360 * (HISTORY_COUNT - index) + 45)
        expires_at = opened_at + timedelta(seconds=duration)
        entry_price = market_data.price_at(symbol, opened_at)
        exit_price = market_data.price_at(symbol, expires_at)
        prior_price = market_data.price_at(symbol, opened_at - timedelta(minutes=1))
        if not entry_price or not exit_price or not prior_price:
            continue

        direction = "call" if entry_price >= prior_price else "put"
        payout = float(universe.get(symbol, {}).get("payouts", {}).get(str(duration), 70))
        stake = round(50 + (index % 5) * 25, 2)

        if abs(exit_price - entry_price) < 1e-12:
            status, net, credit = "void", 0.0, stake
        else:
            won = exit_price > entry_price if direction == "call" else exit_price < entry_price
            status = "won" if won else "lost"
            net = round(stake * payout / 100.0, 2) if won else -stake
            credit = stake + net if won else 0.0

        cash += credit
        db.add(
            BinaryContract(
                org_id=user.org_id,
                user_id=user.id,
                paper_session_id=session.id if session else None,
                mode="paper",
                instrument_symbol=symbol,
                asset_class=universe.get(symbol, {}).get("asset_class", "crypto"),
                direction=direction,
                stake=stake,
                payout_pct=payout,
                duration_seconds=duration,
                entry_price=entry_price,
                exit_price=exit_price,
                price_source="demo",
                is_demo=True,
                status=status,
                net_pnl=net,
                opened_at=opened_at,
                expires_at=expires_at,
                settled_at=expires_at,
                source="demo",
                idempotency_key=f"demo-history-{user.org_id}-{index}",
                entry_reason="Demo history: momentum rule on the previous minute",
            )
        )
        db.add(
            Trade(
                org_id=user.org_id,
                paper_session_id=session.id if session else None,
                mode="paper",
                instrument_symbol=symbol,
                side="long" if direction == "call" else "short",
                quantity=stake,
                entry_price=entry_price,
                exit_price=exit_price,
                notional=stake,
                fees=0.0,
                funding=0.0,
                slippage_est_bps=0.0,
                slippage_actual_bps=0.0,
                gross_pnl=net,
                net_pnl=net,
                entry_reason="Demo history: momentum rule on the previous minute",
                exit_reason=f"binary_expiry:{status}",
                risk_snapshot={
                    "instrument_type": "binary",
                    "direction": direction,
                    "stake": stake,
                    "payout_pct": payout,
                    "duration_seconds": duration,
                    "expiry_price": exit_price,
                    "price_source": "demo",
                    "is_demo": True,
                },
                is_demo=True,
                opened_at=opened_at,
                closed_at=expires_at,
            )
        )

    if session is not None:
        session.cash_balance = round(cash, 2)
        session.equity = round(cash, 2)
        config = dict(session.config or {})
        config["peak_equity"] = max(float(config.get("peak_equity", cash)), cash)
        session.config = config
    db.commit()


def _ensure_position(db, user: User) -> None:
    open_position = (
        db.query(Position)
        .filter(Position.org_id == user.org_id, Position.status == "open")
        .count()
    )
    if open_position:
        return
    from app.trading import engine as trading_engine

    trading_engine.submit_order(
        db,
        user=user,
        request=trading_engine.OrderRequest(
            symbol="ETH/USDT",
            side="buy",
            quantity=0.4,
            order_type="market",
            mode="paper",
            idempotency_key=f"demo-position-{user.org_id}",
            reason="Seeded demo position",
        ),
        source="demo",
    )
    db.commit()


def _reset(db) -> None:
    """Remove the demo account and everything it owns, so the demo can be rebuilt."""
    user = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if user is None:
        return
    org = db.get(Organization, user.org_id)
    db.delete(user)
    db.flush()
    if org is not None:
        db.delete(org)
    db.commit()
    print(f"Removed previous demo account {DEMO_EMAIL}")


def main() -> None:
    seed()
    if "--reset" in sys.argv:
        reset_db = SessionLocal()
        try:
            _reset(reset_db)
        finally:
            reset_db.close()
    db = SessionLocal()
    try:
        user = _demo_user(db)
        _grant_pro(db, user)
        _ensure_session(db, user)
        _ensure_contracts(db, user)
        _ensure_position(db, user)
        print(f"Demo account ready: {DEMO_EMAIL}")
        print(f"  plan=pro  live_trading={'on' if settings.live_trading_enabled else 'off'}  market_data={settings.market_data_source}")
    except AppError as exc:
        db.rollback()
        print(f"Demo seed failed: {exc.detail}", file=sys.stderr)
        raise SystemExit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
