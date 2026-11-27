"""Wallet: what the subscriber actually holds, and how money moves.

VELTRANE never holds client funds. Balances and cash movements live at the connected venue, so
this endpoint reports synced venue balances plus the ledger rows the sync produced, and points
at the venue's own cashier for deposits and withdrawals. Nothing here can move money.
"""

from __future__ import annotations

from app.api import serializers
from app.api.deps import get_current_user
from app.db.models import Balance, Connection, LedgerTransaction, PaperSession, User
from app.db.session import get_db
from app.services.entitlements import resolve_entitlements
from app.services.identity import identity
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

router = APIRouter(prefix="/wallet", tags=["wallet"])

SIMULATED_ACCOUNT_TYPES = {"demo", "virtual", "testnet"}


def _is_simulated(connection: Connection) -> bool:
    return (
        connection.provider == "paper"
        or connection.environment == "paper"
        or (connection.provider_account_type or "").lower() in SIMULATED_ACCOUNT_TYPES
        or bool((connection.provider_meta or {}).get("is_virtual"))
    )


@router.get("")
def wallet(
    limit: int = Query(default=60, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    connections = (
        db.query(Connection)
        .filter(Connection.org_id == user.org_id, Connection.status != "revoked")
        .order_by(Connection.created_at)
        .all()
    )
    by_id = {c.id: c for c in connections}
    balances = (
        db.query(Balance)
        .filter(Balance.org_id == user.org_id)
        .order_by(Balance.usd_value.desc())
        .all()
    )
    session = (
        db.query(PaperSession)
        .filter(PaperSession.org_id == user.org_id, PaperSession.status == "running")
        .order_by(PaperSession.created_at.desc())
        .first()
    )
    transactions = (
        db.query(LedgerTransaction)
        .filter(LedgerTransaction.org_id == user.org_id)
        .order_by(LedgerTransaction.occurred_at.desc())
        .limit(limit)
        .all()
    )

    accounts = []
    for connection in connections:
        rows = [b for b in balances if b.connection_id == connection.id]
        simulated = _is_simulated(connection)
        accounts.append(
            {
                "connection_id": connection.id,
                "label": connection.label,
                "provider": connection.provider,
                "kind": connection.kind,
                "environment": connection.environment,
                "status": connection.status,
                "is_simulated": simulated,
                "account_id": connection.provider_account_id,
                "currency": connection.provider_currency or "USD",
                "balance_usd": round(sum(float(b.usd_value or 0) for b in rows), 2),
                "assets": [
                    {
                        "asset": b.asset,
                        "free": float(b.free),
                        "locked": float(b.locked),
                        "total": float(b.total),
                        "usd_value": float(b.usd_value),
                    }
                    for b in rows
                ],
                "last_sync_at": serializers.iso(connection.last_sync_at),
                "stale": connection.last_sync_at is None,
                "cashier": "provider" if connection.provider != "paper" else "simulated",
            }
        )

    live_total = round(sum(a["balance_usd"] for a in accounts if not a["is_simulated"]), 2)
    demo_total = round(sum(a["balance_usd"] for a in accounts if a["is_simulated"]), 2)
    paper_equity = round(float(session.equity), 2) if session else None

    entries = []
    for txn in transactions:
        connection = by_id.get(txn.connection_id or "")
        entries.append(
            {
                "id": txn.id,
                "type": txn.type,
                "asset": txn.asset,
                "amount": float(txn.amount),
                "fee": float(txn.fee),
                "occurred_at": serializers.iso(txn.occurred_at),
                "reference_type": txn.reference_type,
                "reference_id": txn.reference_id,
                "connection_label": connection.label if connection else None,
                "simulated": _is_simulated(connection) if connection else False,
                "meta": txn.meta or {},
            }
        )

    return {
        "identity": identity(user),
        "totals": {
            "live_usd": live_total,
            "demo_usd": demo_total,
            "paper_equity_usd": paper_equity,
            "currency": "USD",
        },
        "accounts": accounts,
        "transactions": entries,
        "funding": {
            "veltrane_holds_funds": False,
            "method": "provider_cashier",
            "note": (
                "Deposits and withdrawals happen in your exchange or broker account. VELTRANE never "
                "holds client money and cannot move it. Sign in to the provider to fund or withdraw."
            ),
            "providers": sorted({a["provider"] for a in accounts if a["provider"] != "paper"}),
        },
        "entitlements": {"plan_code": resolve_entitlements(db, user.org_id)["plan_code"]},
    }
