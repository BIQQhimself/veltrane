from __future__ import annotations

from app.api import serializers
from app.api.deps import get_current_user
from app.api.schemas import ConnectionCreateRequest, ConnectionRotateRequest
from app.core.errors import forbidden
from app.db.constants import Entitlement
from app.db.models import Balance, Connection, ConnectionCredential, LedgerTransaction, User
from app.db.session import get_db
from app.providers.base import CredentialBundle
from app.providers.registry import provider_catalog
from app.services import connections as connection_service
from app.services import entitlements
from app.services.connections import store_credentials
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter(prefix="/connections", tags=["connections"])


@router.get("/providers")
def providers():
    return {
        "providers": provider_catalog(),
        "notice": (
            "Status values are literal: 'implemented_unverified' means the adapter exists but has not been "
            "verified against a funded account. 'scaffold' means it cannot be used yet."
        ),
    }


@router.get("")
def list_connections(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Connection).filter(Connection.org_id == user.org_id).order_by(Connection.created_at.desc()).all()
    creds = {
        c.connection_id: c
        for c in db.query(ConnectionCredential).filter(ConnectionCredential.org_id == user.org_id).all()
    }
    limit = entitlements.numeric_limit(db, user.org_id, Entitlement.MAX_CONNECTIONS)
    return {
        "connections": [serializers.connection_dict(c, creds.get(c.id)) for c in rows],
        "limit": limit,
        "used": len([c for c in rows if c.status != "revoked"]),
    }


@router.post("", status_code=201)
def create_connection(payload: ConnectionCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    limit = entitlements.numeric_limit(db, user.org_id, Entitlement.MAX_CONNECTIONS)
    used = (
        db.query(Connection)
        .filter(Connection.org_id == user.org_id, Connection.status != "revoked")
        .count()
    )
    if limit is not None and used >= limit:
        entitlements.notify_limit_reached(
            db, user.org_id, "Connection limit reached", f"Your plan allows {limit} connected accounts."
        )
        raise forbidden("connection_limit_reached", f"Your plan allows {limit} connected accounts. Upgrade to add more.")
    connection = connection_service.create_connection(
        db,
        user=user,
        provider_key=payload.provider,
        label=payload.label,
        environment=payload.environment,
        api_key=payload.api_key,
        api_secret=payload.api_secret,
        passphrase=payload.passphrase,
        account_id=payload.account_id,
        withdrawal_attestation=payload.withdrawal_attestation,
    )
    db.commit()
    credential = db.query(ConnectionCredential).filter(ConnectionCredential.connection_id == connection.id).first()
    return serializers.connection_dict(connection, credential)


@router.get("/{connection_id}")
def get_connection(connection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    connection = connection_service.get_connection(db, user.org_id, connection_id)
    credential = db.query(ConnectionCredential).filter(ConnectionCredential.connection_id == connection.id).first()
    return serializers.connection_dict(connection, credential)


@router.post("/{connection_id}/test")
def test_connection(connection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    connection = connection_service.get_connection(db, user.org_id, connection_id)
    result = connection_service.test_connection(db, connection)
    db.commit()
    return result


@router.post("/{connection_id}/sync")
def sync_connection(connection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    connection = connection_service.get_connection(db, user.org_id, connection_id)
    result = connection_service.sync_connection(db, connection)
    db.commit()
    return {**result, "status": connection.status}


@router.post("/{connection_id}/rotate-credentials")
def rotate_credentials(
    connection_id: str,
    payload: ConnectionRotateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    connection = connection_service.get_connection(db, user.org_id, connection_id)
    if connection.provider == "paper":
        raise forbidden("not_applicable", "Simulated connections have no credentials.")
    store_credentials(
        db,
        connection,
        CredentialBundle(api_key=payload.api_key, api_secret=payload.api_secret, passphrase=payload.passphrase),
    )
    db.commit()
    from app.services import audit

    audit.record(
        db,
        action="credential.rotated",
        org_id=user.org_id,
        actor_user_id=user.id,
        target_type="connection",
        target_id=connection.id,
    )
    db.commit()
    credential = db.query(ConnectionCredential).filter(ConnectionCredential.connection_id == connection.id).first()
    return {"status": "rotated", "credential": {"key_hint": credential.key_hint, "rotated_at": serializers.iso(credential.rotated_at)}}


@router.delete("/{connection_id}")
def revoke_connection(connection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    connection = connection_service.get_connection(db, user.org_id, connection_id)
    connection_service.revoke_connection(db, connection, user)
    db.commit()
    return {"status": "revoked"}


@router.get("/{connection_id}/balances")
def balances(connection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    connection = connection_service.get_connection(db, user.org_id, connection_id)
    rows = db.query(Balance).filter(Balance.connection_id == connection.id).order_by(Balance.usd_value.desc()).all()
    return {
        "balances": [
            {
                "asset": b.asset,
                "free": float(b.free),
                "locked": float(b.locked),
                "total": float(b.total),
                "usd_value": float(b.usd_value),
                "as_of": serializers.iso(b.as_of),
            }
            for b in rows
        ],
        "last_sync_at": serializers.iso(connection.last_sync_at),
        "stale": connection.last_sync_at is None,
    }


@router.get("/{connection_id}/transactions")
def transactions(connection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    connection = connection_service.get_connection(db, user.org_id, connection_id)
    rows = (
        db.query(LedgerTransaction)
        .filter(LedgerTransaction.connection_id == connection.id)
        .order_by(LedgerTransaction.occurred_at.desc())
        .limit(200)
        .all()
    )
    return {
        "transactions": [
            {
                "id": t.id,
                "type": t.type,
                "asset": t.asset,
                "amount": float(t.amount),
                "fee": float(t.fee),
                "reference_type": t.reference_type,
                "reference_id": t.reference_id,
                "occurred_at": serializers.iso(t.occurred_at),
                "meta": t.meta,
            }
            for t in rows
        ]
    }
