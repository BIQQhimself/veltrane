"""Explicit multi-step live-trading authorisation.

Live execution requires ALL of the following, in order:
1. Plan entitlement (Pro/Elite).
2. A connected account with trade permission (never withdrawal).
3. Risk-document acknowledgement.
4. A completed safety checklist (every item true).
5. MFA re-verification (or a recorded waiver when the account has no MFA).
6. A time-delayed confirmation token (60s cooling-off) returned to the user.
7. Server-side confirmation with that token.

Plus the process-wide ``VELTRANE_LIVE_TRADING_ENABLED`` env flag, which no API call
can change.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.errors import bad_request, forbidden, not_found
from app.core.security import verify_totp
from app.db.constants import AuditAction, Entitlement, NotificationCategory, Severity
from app.db.models import Connection, TradingPermission, User
from app.services import audit, entitlements, notifications
from app.core.crypto import Envelope, decrypt_json
from sqlalchemy.orm import Session

RISK_DOCUMENT_VERSION = "risk-disclosure-2026-01"

CHECKLIST_ITEMS = {
    "understands_total_loss_risk": "I understand I can lose my entire trading balance.",
    "understands_no_guarantee": "I understand no strategy guarantees profit and past performance is not indicative.",
    "understands_platform_not_advisor": "I understand VELTRANE is not providing personalised financial advice.",
    "understands_costs": "I understand fees, spreads, slippage and funding reduce net returns.",
    "understands_kill_switch": "I know where the kill switch is and how to stop all trading immediately.",
    "understands_credentials": "I will use trade-only API keys without withdrawal permission.",
    "understands_jurisdiction": "I am responsible for compliance with my local laws and tax obligations.",
    "accepts_paper_first": "I have run this strategy in paper mode before enabling live execution.",
}

COOLOFF_SECONDS = 60


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def current_permission(db: Session, org_id: str) -> TradingPermission | None:
    return (
        db.query(TradingPermission)
        .filter(TradingPermission.org_id == org_id)
        .order_by(TradingPermission.created_at.desc())
        .first()
    )


def live_state(db: Session, org_id: str) -> dict:
    perm = current_permission(db, org_id)
    return {
        "platform_live_enabled": settings.live_trading_enabled,
        "entitlement": entitlements.has_feature(db, org_id, Entitlement.LIVE_TRADING),
        "status": perm.status if perm else "not_requested",
        "live_enabled": bool(perm and perm.live_enabled),
        "checklist": perm.checklist if perm else {},
        "checklist_items": CHECKLIST_ITEMS,
        "risk_document_version": RISK_DOCUMENT_VERSION,
        "authorized_at": perm.authorized_at if perm else None,
        "mfa_verified_at": perm.mfa_verified_at if perm else None,
        "confirm_expires_at": perm.confirm_expires_at if perm else None,
        "jurisdiction": perm.jurisdiction if perm else None,
        "note": (
            "Live trading stays disabled until the platform flag is enabled, the plan is eligible, an account is "
            "connected with trade-only keys, and every authorisation step is complete."
        ),
    }


def start_authorization(
    db: Session,
    *,
    user: User,
    acknowledged: bool,
    checklist: dict,
    totp_code: str | None,
    jurisdiction: str,
    connection_id: str | None,
    ip: str | None,
    user_agent: str | None,
) -> dict:
    if not entitlements.has_feature(db, user.org_id, Entitlement.LIVE_TRADING):
        raise forbidden("entitlement_required", "Live trading requires the Pro or Elite plan.")
    if not acknowledged:
        raise bad_request("risk_ack_required", "You must acknowledge the risk disclosure.")
    missing = [key for key, label in CHECKLIST_ITEMS.items() if not checklist.get(key)]
    if missing:
        raise bad_request("checklist_incomplete", "Every safety checklist item must be confirmed.", {"missing": missing})

    connection: Connection | None = None
    if connection_id:
        connection = db.get(Connection, connection_id)
        if connection is None or connection.org_id != user.org_id:
            raise not_found("connection_not_found", "Connection not found.")
    if connection is None:
        connection = (
            db.query(Connection)
            .filter(
                Connection.org_id == user.org_id,
                Connection.status == "connected",
                Connection.environment != "read_only",
            )
            .order_by(Connection.created_at.desc())
            .first()
        )
    if connection is None:
        raise bad_request("connection_required", "Connect a trading-enabled account first.")
    if connection.environment == "read_only" or not connection.permissions.get("trade"):
        raise bad_request("connection_read_only", "This connection is read-only. Add a trade-enabled account.")

    if user.mfa_enabled:
        if not totp_code:
            raise bad_request("mfa_required", "Enter your authenticator code to authorise live trading.")
        if not verify_totp(_mfa_secret(db, user), totp_code):
            raise bad_request("invalid_mfa_code", "The authenticator code is invalid.")
        mfa_verified_at = _utcnow()
    else:
        mfa_verified_at = None

    perm = current_permission(db, user.org_id) or TradingPermission(org_id=user.org_id, user_id=user.id)
    token = secrets.token_urlsafe(32)
    perm.status = "pending_confirmation"
    perm.live_enabled = False
    perm.checklist = checklist
    perm.risk_acknowledged_at = _utcnow()
    perm.mfa_verified_at = mfa_verified_at
    perm.confirm_token_hash = hashlib.sha256(token.encode()).hexdigest()
    perm.confirm_expires_at = _utcnow() + timedelta(seconds=COOLOFF_SECONDS * 10)
    perm.authorization_method = "checklist+ack+mfa" if mfa_verified_at else "checklist+ack"
    perm.jurisdiction = jurisdiction[:2].upper() if jurisdiction else None
    perm.ip = ip
    perm.user_agent = (user_agent or "")[:400] or None
    if perm.id is None:
        db.add(perm)
    db.flush()

    audit.record(
        db,
        action=AuditAction.LIVE_AUTH_REQUESTED,
        org_id=user.org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        target_type="trading_permission",
        target_id=perm.id,
        ip=ip,
        user_agent=user_agent,
        meta={"connection_id": connection.id, "jurisdiction": perm.jurisdiction, "mfa": bool(mfa_verified_at)},
    )
    return {
        "status": "pending_confirmation",
        "confirmation_token": token,
        "cooloff_seconds": COOLOFF_SECONDS,
        "warning": (
            "Confirm after the cooling-off period. Live trading is real money. The platform flag must also be "
            "enabled by the operator before any order can reach a venue."
        ),
    }


def confirm_authorization(db: Session, *, user: User, token: str, ip: str | None = None) -> TradingPermission:
    perm = current_permission(db, user.org_id)
    if perm is None or perm.status != "pending_confirmation":
        raise bad_request("no_pending_authorization", "Start the authorisation flow first.")
    if not perm.confirm_expires_at or perm.confirm_expires_at < _utcnow():
        perm.status = "expired"
        db.flush()
        raise bad_request("confirmation_expired", "The confirmation window expired. Start again.")
    if hashlib.sha256(token.encode()).hexdigest() != perm.confirm_token_hash:
        raise bad_request("invalid_confirmation_token", "Confirmation token is invalid.")
    if perm.risk_acknowledged_at and _utcnow() - perm.risk_acknowledged_at < timedelta(seconds=COOLOFF_SECONDS):
        raise bad_request(
            "cooloff_active",
            f"Please wait {COOLOFF_SECONDS} seconds after acknowledging the risk disclosure before confirming.",
        )
    perm.live_enabled = True
    perm.status = "active"
    perm.authorized_at = _utcnow()
    perm.confirm_token_hash = None
    db.flush()
    audit.record(
        db,
        action=AuditAction.LIVE_AUTH_GRANTED,
        org_id=user.org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        target_type="trading_permission",
        target_id=perm.id,
        ip=ip,
        meta={"jurisdiction": perm.jurisdiction},
    )
    notifications.notify(
        db,
        org_id=user.org_id,
        category=NotificationCategory.SECURITY,
        severity=Severity.CRITICAL,
        title="Live trading authorised",
        body=(
            "Explicit authorisation recorded. Live orders still require the platform operator to enable live "
            "trading and must pass the risk engine on every order."
        ),
        email=True,
    )
    return perm


def revoke_authorization(db: Session, *, user: User, reason: str) -> TradingPermission | None:
    perm = current_permission(db, user.org_id)
    if perm is None:
        return None
    perm.live_enabled = False
    perm.status = "revoked"
    perm.revoked_at = _utcnow()
    perm.revoked_reason = reason[:400]
    db.flush()
    audit.record(
        db,
        action=AuditAction.LIVE_AUTH_REVOKED,
        org_id=user.org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        target_type="trading_permission",
        target_id=perm.id,
        meta={"reason": reason},
    )
    notifications.notify(
        db,
        org_id=user.org_id,
        category=NotificationCategory.SECURITY,
        severity=Severity.WARNING,
        title="Live trading authorisation revoked",
        body="Live order submission is now blocked. Paper trading remains available.",
        email=True,
    )
    return perm


def _mfa_secret(db: Session, user: User) -> str:
    from app.core.crypto import decrypt_json

    if not user.mfa_secret_enc:
        return ""
    try:
        payload = decrypt_json(Envelope.from_json(user.mfa_secret_enc), aad=f"user:{user.id}")
        return payload.get("secret", "")
    except Exception:  # noqa: BLE001
        return ""
