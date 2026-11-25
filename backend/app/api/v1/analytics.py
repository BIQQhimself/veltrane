from __future__ import annotations

from collections import defaultdict

from app.api import serializers
from app.api.deps import get_current_user, get_or_404
from app.db.models import Fee, PaperSession, Position, Strategy, StrategyVersion, Trade, User
from app.db.session import get_db
from app.services import entitlements
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("")
def analytics(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    trades = db.query(Trade).filter(Trade.org_id == user.org_id).order_by(Trade.closed_at.desc()).limit(2000).all()
    advanced = entitlements.has_feature(db, user.org_id, entitlements.Entitlement.ADVANCED_ANALYTICS)

    by_symbol: dict[str, dict] = defaultdict(lambda: {"trades": 0, "net_pnl": 0.0, "wins": 0})
    by_strategy: dict[str, dict] = defaultdict(lambda: {"trades": 0, "net_pnl": 0.0, "wins": 0})
    versions = {v.id: v for v in db.query(StrategyVersion).all()}
    strategies = {s.id: s for s in db.query(Strategy).all()}

    for t in trades:
        for bucket, key in ((by_symbol, t.instrument_symbol), (by_strategy, t.strategy_version_id or "manual")):
            bucket[key]["trades"] += 1
            bucket[key]["net_pnl"] += float(t.net_pnl or 0)
            if float(t.net_pnl or 0) > 0:
                bucket[key]["wins"] += 1

    strategy_rows = []
    for key, data in by_strategy.items():
        label = "Manual / unassigned"
        if key in versions:
            version = versions[key]
            strategy = strategies.get(version.strategy_id)
            label = f"{strategy.name if strategy else 'Unknown'} v{version.version}"
        strategy_rows.append(
            {
                "key": key,
                "label": label,
                "trades": data["trades"],
                "net_pnl": round(data["net_pnl"], 2),
                "win_rate_pct": round(data["wins"] / data["trades"] * 100, 2) if data["trades"] else 0.0,
            }
        )

    fee_rows = db.query(Fee).filter(Fee.org_id == user.org_id).all()
    fee_by_kind: dict[str, float] = defaultdict(float)
    for f in fee_rows:
        fee_by_kind[f.kind] += float(f.amount)

    sessions = db.query(PaperSession).filter(PaperSession.org_id == user.org_id).all()
    open_positions = db.query(Position).filter(Position.org_id == user.org_id, Position.status == "open").all()

    return {
        "advanced_unlocked": advanced,
        "symbols": [
            {"symbol": k, **{**v, "net_pnl": round(v["net_pnl"], 2), "win_rate_pct": round(v["wins"] / v["trades"] * 100, 2) if v["trades"] else 0}}
            for k, v in sorted(by_symbol.items(), key=lambda kv: kv[1]["net_pnl"], reverse=True)
        ],
        "strategies": sorted(strategy_rows, key=lambda r: r["net_pnl"], reverse=True),
        "costs": {
            "by_kind": {k: round(v, 4) for k, v in fee_by_kind.items()},
            "total": round(sum(fee_by_kind.values()), 4),
        },
        "sessions": {
            "total": len(sessions),
            "running": len([s for s in sessions if s.status == "running"]),
        },
        "open_positions": len(open_positions),
        "net_pnl_total": round(sum(float(t.net_pnl or 0) for t in trades), 2),
        "note": "Net of recorded fees. Slippage is shown per trade in the trade detail view.",
    }


@router.get("/trades/{trade_id}/explain")
def explain_trade(trade_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Plain-language explanation of the cost and risk context for one trade."""
    from app.core.errors import not_found

    trade = get_or_404(db, Trade, trade_id)
    if trade is None or trade.org_id != user.org_id:
        raise not_found("trade_not_found", "Trade not found.")
    detail = serializers.trade_detail(db, trade)
    checks = (detail.get("order") or {}).get("risk_decision") or {}
    passed = [c["code"] for c in checks.get("checks", []) if c.get("passed")]
    failed = [c["code"] for c in checks.get("failed_rules", [])]
    return {
        "trade_id": trade.id,
        "summary": {
            "gross": detail["cost_summary"]["gross_pnl"],
            "fees": detail["cost_summary"]["fees"],
            "funding": detail["cost_summary"]["funding"],
            "net": detail["cost_summary"]["net_pnl"],
        },
        "risk_checks_passed": passed,
        "risk_checks_failed": failed,
        "explanation": (
            "Net P&L subtracts trading fees, estimated funding and slippage from the gross move. "
            "The risk engine approved this order only after every blocking rule passed."
            if not failed
            else "This record shows failed rules; review the order audit trail before assuming the trade was valid."
        ),
        "is_demo": trade.is_demo,
    }
