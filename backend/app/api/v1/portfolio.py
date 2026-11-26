from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from app.api import serializers
from app.api.deps import get_current_user
from app.db.models import Balance, Connection, PaperSession, Position, Trade, User
from app.db.session import get_db
from app.services import market_data
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/overview")
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    connections = db.query(Connection).filter(Connection.org_id == user.org_id, Connection.status != "revoked").all()
    balances = db.query(Balance).filter(Balance.org_id == user.org_id).all()
    positions = db.query(Position).filter(Position.org_id == user.org_id, Position.status == "open").all()
    session = (
        db.query(PaperSession)
        .filter(PaperSession.org_id == user.org_id, PaperSession.status == "running")
        .order_by(PaperSession.created_at.desc())
        .first()
    )
    trades = db.query(Trade).filter(Trade.org_id == user.org_id).order_by(Trade.closed_at.desc()).limit(500).all()

    simulated_connection_ids = {
        c.id for c in connections if c.provider == "paper" or c.environment == "paper"
    }
    live_equity = sum(
        float(b.usd_value or 0) for b in balances if b.connection_id not in simulated_connection_ids
    )
    venue_simulated = sum(
        float(b.usd_value or 0) for b in balances if b.connection_id in simulated_connection_ids
    )
    paper_equity = float(session.equity) if session else 0.0
    # A running paper session is the simulated account; its equity supersedes the
    # venue mirror balance so the same virtual capital is never counted twice.
    simulated_balance = paper_equity if session else venue_simulated
    unrealised = sum(float(p.unrealized_pnl or 0) for p in positions)
    realized = sum(float(t.net_pnl or 0) for t in trades)
    fees = sum(float(t.fees or 0) for t in trades)

    allocation: dict[str, float] = defaultdict(float)
    for b in balances:
        allocation[b.asset] += float(b.usd_value or 0)
    for p in positions:
        value = abs(float(p.quantity) * float(p.mark_price or p.avg_entry_price))
        allocation[p.instrument_symbol] += value

    return {
        "equity": {
            "live_balance_usd": round(live_equity, 2),
            "simulated_balance_usd": round(simulated_balance, 2),
            "paper_equity_usd": round(paper_equity, 2),
            "total_usd": round(live_equity + simulated_balance, 2),
            "simulated_source": "paper_session" if session else ("venue_balances" if venue_simulated else "none"),
            "unrealized_pnl": round(unrealised, 2),
            "realized_pnl_net": round(realized, 2),
            "fees_paid": round(fees, 4),
            "currency": "USD",
        },
        "connections": [serializers.connection_dict(c) for c in connections],
        "balances": [
            {
                "asset": b.asset,
                "free": float(b.free),
                "locked": float(b.locked),
                "total": float(b.total),
                "usd_value": float(b.usd_value),
                "as_of": serializers.iso(b.as_of),
                "connection_id": b.connection_id,
            }
            for b in balances
        ],
        "positions": [serializers.position_dict(p) for p in positions],
        "allocation": [
            {"label": k, "value": round(v, 2)} for k, v in sorted(allocation.items(), key=lambda kv: kv[1], reverse=True)
        ],
        "paper_session": serializers.session_dict(session) if session else None,
        "has_live_data": bool(live_equity),
        "note": (
            "Balances come from read-only account syncs. Paper equity is simulated and clearly separated. "
            "No funds are held by VELTRANE."
        ),
    }


@router.get("/performance")
def performance(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    trades = (
        db.query(Trade)
        .filter(Trade.org_id == user.org_id)
        .order_by(Trade.closed_at.asc())
        .limit(2000)
        .all()
    )
    daily: dict[str, float] = defaultdict(float)
    cumulative = 0.0
    curve = []
    for t in trades:
        day = t.closed_at.date().isoformat()
        daily[day] += float(t.net_pnl or 0)
    for day in sorted(daily):
        cumulative += daily[day]
        curve.append({"date": day, "pnl": round(daily[day], 2), "cumulative": round(cumulative, 2)})

    wins = [t for t in trades if float(t.net_pnl) > 0]
    losses = [t for t in trades if float(t.net_pnl) <= 0]
    gross_win = sum(float(t.net_pnl) for t in wins)
    gross_loss = abs(sum(float(t.net_pnl) for t in losses))
    peak = 0.0
    max_dd = 0.0
    equity = 0.0
    for point in curve:
        equity = point["cumulative"]
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100)

    return {
        "curve": curve,
        "stats": {
            "trades": len(trades),
            "win_rate_pct": round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
            "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else None,
            "avg_win": round(gross_win / len(wins), 2) if wins else 0.0,
            "avg_loss": round(-gross_loss / len(losses), 2) if losses else 0.0,
            "net_pnl": round(sum(float(t.net_pnl) for t in trades), 2),
            "fees": round(sum(float(t.fees) for t in trades), 4),
            "max_drawdown_pct": round(max_dd, 2),
            "paper_trades": len([t for t in trades if t.mode == "paper"]),
            "live_trades": len([t for t in trades if t.mode == "live"]),
        },
        "note": "All figures are net of recorded fees. Paper and live trades are counted separately above.",
    }


@router.get("/markets")
def market_overview(user: User = Depends(get_current_user)):
    rows = []
    for item in market_data.supported_symbols():
        try:
            snap = market_data.get_ticker(item["symbol"])
            rows.append({**item, "price": snap.price, "is_demo": snap.is_demo, "source": snap.source})
        except Exception as exc:  # noqa: BLE001
            rows.append({**item, "price": None, "error": str(exc)[:120], "is_demo": True})
    return {"markets": rows, "as_of": datetime.now(UTC).isoformat()}
