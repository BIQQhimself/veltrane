from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.crypto import Envelope, decrypt_json, encrypt_json
from app.core.errors import bad_request, conflict, forbidden, unauthorized
from app.core.security import (
    create_token,
    generate_recovery_codes,
    generate_totp_secret,
    hash_password,
    hash_recovery_code,
    hash_token,
    password_strength_errors,
    totp_provisioning_uri,
    verify_password,
    verify_totp,
)
from app.db.constants import AuditAction, NotificationCategory, Severity, UserStatus
from app.db.models import OneTimeToken, Organization, RefreshSession, User
from app.services import audit, billing, notifications
from app.services.email import queue_email
from sqlalchemy.orm import Session

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(email: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", email.split("@")[0].lower()).strip("-") or "workspace"
    return f"{base[:48]}-{secrets.token_hex(3)}"


def register(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str,
    country: str | None,
    terms_version: str,
    ip: str | None,
    user_agent: str | None,
) -> tuple[User, str | None]:
    email = email.strip().lower()
    errors = password_strength_errors(password)
    if errors:
        raise bad_request("weak_password", "Password must contain " + ", ".join(errors) + ".")
    if db.query(User).filter(User.email == email).first():
        raise conflict("email_in_use", "An account with that email already exists.")

    org = Organization(name=full_name.strip()[:160] or email, slug=_slugify(email), country=country, timezone="UTC")
    db.add(org)
    db.flush()

    user = User(
        org_id=org.id,
        email=email,
        password_hash=hash_password(password),
        full_name=full_name.strip()[:160],
        status=UserStatus.PENDING,
        terms_accepted_at=_utcnow(),
        terms_version=terms_version,
    )
    db.add(user)
    db.flush()

    billing.ensure_free_subscription(db, org.id)
    token, plaintext = _issue_one_time_token(db, user, purpose="verify_email", hours=48)
    queue_email(
        db,
        to_email=email,
        subject="Verify your VELTRANE account",
        body=(
            f"Welcome to VELTRANE.\n\nVerify your email within 48 hours:\n"
            f"{settings.web_base_url}/verify-email?token={plaintext}\n\n"
            "This platform never custodies funds and never requests withdrawal permission on exchange keys."
        ),
        category="security",
    )
    audit.record(
        db,
        action=AuditAction.USER_REGISTERED,
        org_id=org.id,
        actor_user_id=user.id,
        actor_email=email,
        ip=ip,
        user_agent=user_agent,
        meta={"country": country},
    )
    debug_token = plaintext if not settings.is_production else None
    return user, debug_token


def _issue_one_time_token(db: Session, user: User, *, purpose: str, hours: int) -> tuple[OneTimeToken, str]:
    raw = secrets.token_urlsafe(32)
    record = OneTimeToken(
        user_id=user.id,
        purpose=purpose,
        token_hash=hash_token(raw),
        expires_at=_utcnow() + timedelta(hours=hours),
    )
    db.add(record)
    db.flush()
    return record, raw


def verify_email(db: Session, *, token: str) -> User:
    record = db.query(OneTimeToken).filter(OneTimeToken.token_hash == hash_token(token)).first()
    if record is None or record.purpose != "verify_email":
        raise bad_request("invalid_token", "This verification link is not valid.")
    if record.used_at is not None:
        raise bad_request("token_used", "This verification link has already been used.")
    if record.expires_at < _utcnow():
        raise bad_request("token_expired", "This verification link has expired. Request a new one.")
    user = db.get(User, record.user_id)
    if user is None:
        raise bad_request("invalid_token", "This verification link is not valid.")
    user.email_verified_at = _utcnow()
    if user.status == UserStatus.PENDING:
        user.status = UserStatus.ACTIVE
    record.used_at = _utcnow()
    db.flush()
    audit.record(db, action="user.email_verified", org_id=user.org_id, actor_user_id=user.id, actor_email=user.email)
    return user


def resend_verification(db: Session, *, email: str) -> str | None:
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if user is None or user.email_verified_at is not None:
        return None
    _, plaintext = _issue_one_time_token(db, user, purpose="verify_email", hours=48)
    queue_email(
        db,
        to_email=user.email,
        subject="Verify your VELTRANE account",
        body=f"Verify your email within 48 hours:\n{settings.web_base_url}/verify-email?token={plaintext}",
        category="security",
    )
    return plaintext if not settings.is_production else None


def authenticate(
    db: Session, *, email: str, password: str, ip: str | None, user_agent: str | None
) -> tuple[User, bool]:
    """Return (user, mfa_required). Raises on failure with a generic message."""
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    generic = unauthorized("invalid_credentials", "Email or password is incorrect.")
    if user is None:
        audit.record(db, action=AuditAction.USER_LOGIN_FAILED, actor_email=email, ip=ip, meta={"reason": "unknown_email"})
        db.commit()  # audit must persist even though the request fails
        raise generic
    if user.locked_until and user.locked_until > _utcnow():
        raise forbidden("account_locked", "Too many failed attempts. Try again later.")
    if user.status in (UserStatus.SUSPENDED, UserStatus.DELETED):
        raise forbidden("account_suspended", "This account is not available. Contact support.")
    if not verify_password(password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_LOGINS:
            user.locked_until = _utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_attempts = 0
        audit.record(
            db,
            action=AuditAction.USER_LOGIN_FAILED,
            org_id=user.org_id,
            actor_user_id=user.id,
            actor_email=email,
            ip=ip,
            meta={"reason": "bad_password"},
        )
        db.commit()
        raise generic
    if settings.require_email_verification and user.email_verified_at is None:
        raise forbidden("email_unverified", "Verify your email address before signing in.")
    if user.status == UserStatus.PENDING:
        user.status = UserStatus.ACTIVE
    user.failed_login_attempts = 0
    user.locked_until = None
    db.flush()
    return user, user.mfa_enabled


def complete_login(db: Session, *, user: User, ip: str | None, user_agent: str | None) -> dict:
    user.last_login_at = _utcnow()
    db.flush()
    audit.record(
        db,
        action=AuditAction.USER_LOGIN,
        org_id=user.org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        actor_role=user.staff_role,
        ip=ip,
        user_agent=user_agent,
    )
    return issue_session(db, user=user, ip=ip, user_agent=user_agent)


def issue_session(db: Session, *, user: User, ip: str | None, user_agent: str | None) -> dict:
    version = int(user.token_version or 1)
    access, _, access_exp = create_token(
        subject=user.id,
        token_type="access",
        org_id=user.org_id,
        role="staff" if user.is_staff else "member",
        extra={"ver": version},
    )
    refresh, refresh_jti, refresh_exp = create_token(
        subject=user.id, token_type="refresh", org_id=user.org_id, extra={"ver": version}
    )
    db.add(
        RefreshSession(
            user_id=user.id,
            jti=refresh_jti,
            token_hash=hash_token(refresh),
            user_agent=(user_agent or "")[:400] or None,
            ip=ip,
            expires_at=refresh_exp,
        )
    )
    db.flush()
    return {
        "access_token": access,
        "token_type": "bearer",
        "expires_at": access_exp,
        "refresh_token": refresh,
        "refresh_expires_at": refresh_exp,
    }


def rotate_refresh(db: Session, *, refresh_token: str, ip: str | None, user_agent: str | None) -> dict:
    from app.core.security import decode_token

    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except ValueError:
        raise unauthorized("invalid_refresh_token", "Session expired. Sign in again.")
    session = db.query(RefreshSession).filter(RefreshSession.jti == payload["jti"]).first()
    if session is None or session.token_hash != hash_token(refresh_token):
        raise unauthorized("invalid_refresh_token", "Session expired. Sign in again.")
    if session.revoked_at is not None or session.expires_at < _utcnow():
        raise unauthorized("refresh_token_revoked", "Session expired. Sign in again.")
    user = db.get(User, session.user_id)
    if user is None or user.status in (UserStatus.SUSPENDED, UserStatus.DELETED):
        raise unauthorized("account_unavailable", "This account is not available.")
    session.revoked_at = _utcnow()
    issued = issue_session(db, user=user, ip=ip, user_agent=user_agent)
    session.replaced_by = decode_token(issued["refresh_token"], expected_type="refresh")["jti"]
    db.flush()
    return issued


def revoke_refresh(db: Session, *, refresh_token: str) -> None:
    from app.core.security import decode_token

    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except ValueError:
        return
    session = db.query(RefreshSession).filter(RefreshSession.jti == payload["jti"]).first()
    if session and session.revoked_at is None:
        session.revoked_at = _utcnow()
        db.flush()


def logout_all(db: Session, user: User) -> int:
    user.token_version = int(user.token_version or 1) + 1
    count = (
        db.query(RefreshSession)
        .filter(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))
        .update({RefreshSession.revoked_at: _utcnow()})
    )
    db.flush()
    audit.record(db, action=AuditAction.USER_LOGOUT, org_id=user.org_id, actor_user_id=user.id, meta={"sessions": count})
    return count


def change_password(db: Session, *, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise bad_request("invalid_password", "Current password is incorrect.")
    errors = password_strength_errors(new)
    if errors:
        raise bad_request("weak_password", "Password must contain " + ", ".join(errors) + ".")
    user.password_hash = hash_password(new)
    db.flush()
    logout_all(db, user)
    audit.record(db, action=AuditAction.PASSWORD_CHANGED, org_id=user.org_id, actor_user_id=user.id)
    notifications.notify(
        db,
        org_id=user.org_id,
        user_id=user.id,
        category=NotificationCategory.SECURITY,
        severity=Severity.WARNING,
        title="Password changed",
        body="All sessions were signed out. If this was not you, contact support immediately.",
        email=True,
    )


def setup_mfa(db: Session, *, user: User) -> dict:
    secret = generate_totp_secret()
    envelope = encrypt_json({"secret": secret}, aad=f"user:{user.id}")
    user.mfa_secret_enc = envelope.as_json()
    user.mfa_enabled = False
    db.flush()
    return {"secret": secret, "otpauth_uri": totp_provisioning_uri(secret, user.email)}


def enable_mfa(db: Session, *, user: User, code: str) -> list[str]:
    secret = _user_mfa_secret(user)
    if not secret:
        raise bad_request("mfa_not_initialised", "Start MFA setup first.")
    if not verify_totp(secret, code):
        raise bad_request("invalid_mfa_code", "That code is not valid.")
    recovery = generate_recovery_codes()
    user.mfa_recovery_hashes = [hash_recovery_code(c) for c in recovery]
    user.mfa_enabled = True
    db.flush()
    audit.record(db, action=AuditAction.MFA_ENABLED, org_id=user.org_id, actor_user_id=user.id)
    notifications.notify(
        db,
        org_id=user.org_id,
        user_id=user.id,
        category=NotificationCategory.SECURITY,
        severity=Severity.INFO,
        title="Two-factor authentication enabled",
        body="Live-trading authorisation now requires an authenticator code.",
        email=True,
    )
    return recovery


def disable_mfa(db: Session, *, user: User, password: str) -> None:
    if not verify_password(password, user.password_hash):
        raise bad_request("invalid_password", "Password is incorrect.")
    user.mfa_enabled = False
    user.mfa_secret_enc = None
    user.mfa_recovery_hashes = []
    db.flush()
    audit.record(db, action=AuditAction.MFA_DISABLED, org_id=user.org_id, actor_user_id=user.id)
    notifications.notify(
        db,
        org_id=user.org_id,
        user_id=user.id,
        category=NotificationCategory.SECURITY,
        severity=Severity.CRITICAL,
        title="Two-factor authentication disabled",
        body="Your account is less protected. Re-enable 2FA as soon as possible.",
        email=True,
    )


def verify_mfa_login(db: Session, *, user: User, code: str, ip: str | None, user_agent: str | None) -> dict:
    secret = _user_mfa_secret(user)
    if verify_totp(secret, code):
        return complete_login(db, user=user, ip=ip, user_agent=user_agent)
    digest = hash_recovery_code(code)
    if digest in (user.mfa_recovery_hashes or []):
        remaining = [h for h in user.mfa_recovery_hashes if h != digest]
        user.mfa_recovery_hashes = remaining
        db.flush()
        audit.record(
            db,
            action=AuditAction.USER_LOGIN,
            org_id=user.org_id,
            actor_user_id=user.id,
            actor_email=user.email,
            ip=ip,
            meta={"method": "recovery_code", "remaining": len(remaining)},
        )
        return issue_session(db, user=user, ip=ip, user_agent=user_agent)
    raise bad_request("invalid_mfa_code", "That code is not valid.")


def request_password_reset(db: Session, *, email: str) -> str | None:
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if user is None:
        return None
    _, plaintext = _issue_one_time_token(db, user, purpose="reset_password", hours=1)
    queue_email(
        db,
        to_email=user.email,
        subject="Reset your VELTRANE password",
        body=f"Reset your password within one hour:\n{settings.web_base_url}/reset-password?token={plaintext}",
        category="security",
    )
    return plaintext if not settings.is_production else None


def reset_password(db: Session, *, token: str, new_password: str) -> None:
    record = db.query(OneTimeToken).filter(OneTimeToken.token_hash == hash_token(token)).first()
    if record is None or record.purpose != "reset_password" or record.used_at or record.expires_at < _utcnow():
        raise bad_request("invalid_token", "This reset link is invalid or expired.")
    errors = password_strength_errors(new_password)
    if errors:
        raise bad_request("weak_password", "Password must contain " + ", ".join(errors) + ".")
    user = db.get(User, record.user_id)
    if user is None:
        raise bad_request("invalid_token", "This reset link is invalid or expired.")
    user.password_hash = hash_password(new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    record.used_at = _utcnow()
    db.flush()
    logout_all(db, user)
    audit.record(db, action=AuditAction.PASSWORD_CHANGED, org_id=user.org_id, actor_user_id=user.id, meta={"via": "reset"})
    notifications.notify(
        db,
        org_id=user.org_id,
        user_id=user.id,
        category=NotificationCategory.SECURITY,
        severity=Severity.WARNING,
        title="Password reset completed",
        body="All sessions were signed out.",
        email=True,
    )


def _user_mfa_secret(user: User) -> str:
    if not user.mfa_secret_enc:
        return ""
    try:
        return decrypt_json(Envelope.from_json(user.mfa_secret_enc), aad=f"user:{user.id}").get("secret", "")
    except Exception:  # noqa: BLE001
        return ""
