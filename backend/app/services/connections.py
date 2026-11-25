from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from app.core.crypto import DecryptionError, Envelope, decrypt_json, encrypt_json, mask_secret
from app.core.errors import bad_request, conflict, not_found
from app.db.constants import (
    AuditAction,
    ConnectionEnvironment,
    ConnectionStatus,
    NotificationCategory,
    Severity,
)
from app.db.models import Balance, Connection, ConnectionCredential, Position, User
from app.providers.base import CredentialBundle, ProviderError
from app.providers.registry import get_provider
from app.services import audit, notifications
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aad(org_id: str, connection_id: str) -> str:
    return f"org:{org_id}|connection:{connection_id}"


def store_credentials(db: Session, connection: Connection, bundle: CredentialBundle) -> ConnectionCredential:
    payload = {
        "api_key": bundle.api_key,
        "api_secret": bundle.api_secret,
        "passphrase": bundle.passphrase,
        "account_id": bundle.account_id,
        "app_id": bundle.app_id,
    }
    envelope = encrypt_json(payload, aad=_aad(connection.org_id, connection.id))
    fingerprint = hashlib.sha256(f"{connection.org_id}:{bundle.api_key}".encode()).hexdigest()[:32]
    existing = db.query(ConnectionCredential).filter(ConnectionCredential.connection_id == connection.id).first()
    if existing:
        existing.envelope = envelope.as_json()
        existing.kek_version = envelope.kek_version
        existing.key_hint = mask_secret(bundle.api_key)
        existing.fingerprint = fingerprint
        existing.rotated_at = utcnow()
        db.flush()
        return existing
    credential = ConnectionCredential(
        org_id=connection.org_id,
        connection_id=connection.id,
        envelope=envelope.as_json(),
        kek_version=envelope.kek_version,
        key_hint=mask_secret(bundle.api_key),
        fingerprint=fingerprint,
    )
    db.add(credential)
    db.flush()
    return credential


def load_credentials(db: Session, connection: Connection) -> CredentialBundle:
    credential = db.query(ConnectionCredential).filter(ConnectionCredential.connection_id == connection.id).first()
    if credential is None:
        raise bad_request("no_credentials", "This connection has no stored credentials.")
    try:
        payload = decrypt_json(Envelope.from_json(credential.envelope), aad=_aad(connection.org_id, connection.id))
    except DecryptionError as exc:
        log.error("credential_decryption_failed", extra={"extra_fields": {"connection_id": connection.id}})
        raise bad_request("credential_unreadable", "Stored credentials could not be decrypted. Re-enter them.") from exc
    return CredentialBundle(
        api_key=payload.get("api_key", ""),
        api_secret=payload.get("api_secret", ""),
        passphrase=payload.get("passphrase", ""),
        account_id=payload.get("account_id", ""),
        app_id=payload.get("app_id", ""),
    )


def create_connection(
    db: Session,
    *,
    user: User,
    provider_key: str,
    label: str,
    environment: str,
    api_key: str = "",
    api_secret: str = "",
    passphrase: str = "",
    account_id: str = "",
    withdrawal_attestation: bool = False,
) -> Connection:
    provider = get_provider(provider_key)
    if environment not in (ConnectionEnvironment.READ_ONLY, ConnectionEnvironment.PAPER, ConnectionEnvironment.LIVE):
        raise bad_request("invalid_environment", "Environment must be read_only, paper or live.")
    if environment == ConnectionEnvironment.LIVE and provider.info.status == "scaffold":
        raise bad_request(
            "provider_not_ready",
            f"{provider.info.name} is not implemented for live use in this build. Read-only is unavailable too.",
        )
    if provider.info.status == "scaffold":
        raise bad_request(
            "provider_not_implemented",
            f"{provider.info.name} is a documented scaffold. It cannot be connected yet.",
        )
    if environment != ConnectionEnvironment.PAPER and (not api_key or not api_secret):
        raise bad_request("missing_credentials", "API key and secret are required for a real connection.")
    if environment == ConnectionEnvironment.PAPER and provider_key != "paper":
        # A paper environment is local simulation; no venue keys needed.
        environment = ConnectionEnvironment.PAPER

    duplicate = (
        db.query(Connection)
        .filter(Connection.org_id == user.org_id, Connection.label == label)
        .first()
    )
    if duplicate:
        raise conflict("label_in_use", "You already have a connection with that label.")

    connection = Connection(
        org_id=user.org_id,
        created_by=user.id,
        kind=provider.info.kind,
        provider=provider_key,
        label=label[:80],
        environment=environment,
        status=ConnectionStatus.PENDING,
        permissions={
            "read": True,
            "trade": environment != ConnectionEnvironment.READ_ONLY and provider_key != "paper",
            "withdraw": False,
            "withdrawal_attestation": bool(withdrawal_attestation),
        },
        capabilities=provider.capabilities.as_dict(),
    )
    db.add(connection)
    db.flush()

    if api_key and api_secret:
        store_credentials(db, connection, CredentialBundle(api_key=api_key, api_secret=api_secret, passphrase=passphrase, account_id=account_id))
    else:
        connection.status = ConnectionStatus.CONNECTED
        connection.permissions = {**connection.permissions, "simulated": True}

    audit.record(
        db,
        action=AuditAction.CONNECTION_CREATED,
        org_id=user.org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        target_type="connection",
        target_id=connection.id,
        meta={"provider": provider_key, "environment": environment, "label": label},
    )
    return connection


def test_connection(db: Session, connection: Connection) -> dict:
    if connection.environment == ConnectionEnvironment.PAPER or connection.provider == "paper":
        connection.status = ConnectionStatus.CONNECTED
        connection.last_error = None
        db.flush()
        return {"ok": True, "mode": "paper", "note": "Simulated connection — no venue keys involved."}
    provider = get_provider(connection.provider)
    try:
        credentials = load_credentials(db, connection)
        result = provider.test_connection(credentials)
    except ProviderError as exc:
        connection.status = ConnectionStatus.ERROR
        connection.last_error = exc.message[:1000]
        connection.last_error_at = utcnow()
        db.flush()
        notifications.notify(
            db,
            org_id=connection.org_id,
            category=NotificationCategory.CONNECTION,
            severity=Severity.WARNING,
            title=f"Connection test failed: {connection.label}",
            body=f"{exc.message} No orders will be routed until this is resolved.",
            data={"connection_id": connection.id},
        )
        db.commit()  # persist the error state and notification before surfacing the failure
        raise bad_request(exc.code, exc.message)
    connection.status = ConnectionStatus.CONNECTED
    connection.last_error = None
    permissions = result.get("permissions") or {}
    connection.permissions = {
        **connection.permissions,
        "withdrawal_scope": permissions.get("withdrawal_scope", "unknown"),
        "withdrawal_verified": bool(permissions.get("verified", False)),
        "balance_currencies": result.get("balance_currencies", []),
    }
    db.flush()
    if simulated:
        connection.status = ConnectionStatus.CONNECTED
    audit.record(
        db,
        action=AuditAction.CONNECTION_SYNCED,
        org_id=connection.org_id,
        target_type="connection",
        target_id=connection.id,
        meta={"operation": "test_connection", "provider": connection.provider},
    )
    return {"ok": True, **result}


def sync_connection(db: Session, connection: Connection) -> dict:
    if connection.status == ConnectionStatus.REVOKED:
        raise bad_request("connection_revoked", "This connection has been revoked.")
    provider = get_provider(connection.provider)
    simulated = connection.provider == "paper" or connection.environment == ConnectionEnvironment.PAPER
    try:
        credentials = CredentialBundle() if simulated else load_credentials(db, connection)
        balances = provider.fetch_balances(credentials)
        positions = provider.fetch_positions(credentials)
    except ProviderError as exc:
        connection.status = ConnectionStatus.ERROR
        connection.last_error = exc.message[:1000]
        connection.last_error_at = utcnow()
        db.flush()
        notifications.notify(
            db,
            org_id=connection.org_id,
            category=NotificationCategory.CONNECTION,
            severity=Severity.WARNING,
            title=f"Sync failed: {connection.label}",
            body=f"{exc.message} Displayed balances may be out of date.",
            data={"connection_id": connection.id},
        )
        db.commit()  # persist the error state and notification before surfacing the failure
        raise bad_request(exc.code, exc.message)

    now = utcnow()
    db.query(Balance).filter(Balance.connection_id == connection.id).delete()
    for row in balances:
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
    db.query(Position).filter(
        Position.connection_id == connection.id, Position.mode == "live", Position.status == "open"
    ).delete()
    for row in positions:
        db.add(
            Position(
                org_id=connection.org_id,
                mode="live",
                connection_id=connection.id,
                instrument_symbol=row["symbol"],
                side=row.get("side") or "long",
                quantity=row.get("quantity", 0),
                avg_entry_price=row.get("entry_price", 0),
                mark_price=row.get("mark_price", 0),
                unrealized_pnl=row.get("unrealized_pnl", 0),
                leverage=row.get("leverage", 1),
                status="open",
                opened_at=now,
            )
        )
    connection.last_sync_at = now
    connection.status = ConnectionStatus.CONNECTED
    connection.last_error = None
    db.flush()
    if simulated:
        connection.status = ConnectionStatus.CONNECTED
    audit.record(
        db,
        action=AuditAction.CONNECTION_SYNCED,
        org_id=connection.org_id,
        target_type="connection",
        target_id=connection.id,
        meta={"balances": len(balances), "positions": len(positions)},
    )
    return {"balances": len(balances), "positions": len(positions), "synced_at": now}


def revoke_connection(db: Session, connection: Connection, actor: User, reason: str = "user_request") -> Connection:
    connection.status = ConnectionStatus.REVOKED
    connection.revoked_at = utcnow()
    db.query(ConnectionCredential).filter(ConnectionCredential.connection_id == connection.id).delete()
    db.flush()
    audit.record(
        db,
        action=AuditAction.CONNECTION_REVOKED,
        org_id=connection.org_id,
        actor_user_id=actor.id,
        actor_email=actor.email,
        target_type="connection",
        target_id=connection.id,
        meta={"reason": reason},
    )
    notifications.notify(
        db,
        org_id=connection.org_id,
        category=NotificationCategory.CONNECTION,
        severity=Severity.INFO,
        title=f"Connection revoked: {connection.label}",
        body="Stored credentials were deleted. Any running paper session continues in simulation only.",
    )
    return connection


def get_connection(db: Session, org_id: str, connection_id: str) -> Connection:
    connection = db.get(Connection, connection_id)
    if connection is None or connection.org_id != org_id:
        raise not_found("connection_not_found", "Connection not found.")
    return connection


def serialise(connection: Connection, credential: ConnectionCredential | None = None) -> dict:
    """Public representation. Credential material is never included."""
    return {
        "id": connection.id,
        "provider": connection.provider,
        "kind": connection.kind,
        "label": connection.label,
        "environment": connection.environment,
        "status": connection.status,
        "permissions": connection.permissions,
        "capabilities": connection.capabilities,
        "is_sandbox": connection.is_sandbox,
        "last_sync_at": connection.last_sync_at,
        "last_error": connection.last_error,
        "last_error_at": connection.last_error_at,
        "created_at": connection.created_at,
        "revoked_at": connection.revoked_at,
        "credential": (
            {
                "key_hint": credential.key_hint,
                "fingerprint": credential.fingerprint,
                "rotated_at": credential.rotated_at,
                "kek_version": credential.kek_version,
            }
            if credential
            else None
        ),
    }
