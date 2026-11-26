from __future__ import annotations

from datetime import UTC, datetime

from app.api.deps import get_current_user
from app.api.schemas import BinaryContractRequest, BinaryQuoteRequest
from app.core.config import settings
from app.core.rate_limit import enforce
from app.db.models import BinaryContract, User
from app.db.session import get_db
from app.trading import binary as binary_engine
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

router = APIRouter(prefix="/binary", tags=["binary"])


def contract_dict(contract: BinaryContract) -> dict:
    return {
        "id": contract.id,
        "symbol": contract.instrument_symbol,
        "asset_class": contract.asset_class,
        "direction": contract.direction,
        "stake": float(contract.stake),
        "payout_pct": float(contract.payout_pct),
        "potential_return": round(float(contract.stake) * float(contract.payout_pct) / 100.0, 2),
        "duration_seconds": contract.duration_seconds,
        "entry_price": float(contract.entry_price),
        "exit_price": float(contract.exit_price) if contract.exit_price is not None else None,
        "status": contract.status,
        "net_pnl": float(contract.net_pnl),
        "opened_at": contract.opened_at,
        "expires_at": contract.expires_at,
        "settled_at": contract.settled_at,
        "seconds_remaining": (
            max(0, int((contract.expires_at - datetime.now(UTC)).total_seconds()))
            if contract.status == "open"
            else 0
        ),
        "source": contract.source,
        "entry_reason": contract.entry_reason,
        "rejection_reason": contract.rejection_reason,
        "price_source": contract.price_source,
        "is_demo": contract.is_demo,
        "mode": contract.mode,
        "risk": contract.risk_snapshot,
        "risk_decision_id": contract.risk_decision_id,
    }


@router.get("/assets")
def assets():
    return {
        "assets": binary_engine.asset_universe(),
        "durations": list(binary_engine.ALLOWED_DURATIONS),
        "min_stake": settings.binary_min_stake,
        "max_stake": settings.binary_max_stake,
        "mode": "paper",
        "note": "Binary contracts are simulated in this build. No live binary venue is connected.",
    }


@router.post("/quote")
def quote(payload: BinaryQuoteRequest, request: Request, user: User = Depends(get_current_user)):
    enforce(request, "binary_quote", limit=120, window=60)
    return binary_engine.quote(payload.symbol, payload.duration_seconds)


@router.post("/contracts", status_code=201)
def open_contract(
    payload: BinaryContractRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce(request, "binary_orders", limit=30, window=60)
    result = binary_engine.open_contract(
        db,
        user=user,
        symbol=payload.symbol,
        direction=payload.direction,
        stake=payload.stake,
        duration_seconds=payload.duration_seconds,
        source="human",
        reason=payload.reason,
        idempotency_key=payload.idempotency_key,
    )
    contract = result["contract"]
    decision = result["decision"]
    return {
        "idempotent_replay": result["idempotent_replay"],
        "approved": contract.status == "open",
        "contract": contract_dict(contract),
        "risk_decision": {
            "decision": decision.decision,
            "failed_rules": decision.failed_rules,
            "checks": decision.checks,
            "policy_version": decision.policy_version,
        }
        if decision
        else None,
        "disclaimer": "Simulated contract. No real order was placed and no funds moved.",
    }


@router.get("/contracts")
def list_contracts(
    status: str | None = None,
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    binary_engine.settle_due(db, org_id=user.org_id)
    rows = binary_engine.list_contracts(db, org_id=user.org_id, status=status, limit=limit)
    return {
        "contracts": [contract_dict(c) for c in rows],
        "summary": binary_engine.summary(db, org_id=user.org_id),
        "is_demo": True,
    }


@router.get("/summary")
def summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    binary_engine.settle_due(db, org_id=user.org_id)
    return binary_engine.summary(db, org_id=user.org_id)


@router.post("/settle")
def settle(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Force a settlement pass for expired contracts. Idempotent and safe to call often."""
    settled = binary_engine.settle_due(db, org_id=user.org_id)
    return {
        "settled": [contract_dict(c) for c in settled],
        "count": len(settled),
        "summary": binary_engine.summary(db, org_id=user.org_id),
    }
