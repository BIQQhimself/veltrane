"""Deriv OAuth 2.0 (authorization code + PKCE).

Flow, exactly as documented at developers.deriv.com/docs/intro/oauth:

1. VELTRANE generates a PKCE verifier, its S256 challenge, and a random ``state``.
2. The browser is sent to ``https://auth.deriv.com/oauth2/auth`` with the client id,
   the registered redirect URI, the requested scopes and the challenge.
3. Deriv authenticates the user (or shows its own signup form) and redirects back with
   ``code`` and ``state``.
4. The backend verifies ``state`` (single use, bound to the user, short lived), then posts
   ``grant_type=authorization_code`` to ``https://auth.deriv.com/oauth2/token``.
5. The access token is stored encrypted in the same envelope as other credentials.

Deriv issues no refresh token, so an expired token means one more trip through the flow.
The expiry is stored so the product can say so before a trade fails.

Scopes: only the four Deriv documents are accepted (``trade``, ``account_manage``,
``application_read``, ``payment``). VELTRANE asks for ``trade`` and ``account_manage`` by
default and never for ``payment``, because payment covers withdrawal operations.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from app.core.config import settings
from app.core.crypto import Envelope, decrypt_json, encrypt_json
from app.core.errors import bad_request, conflict, forbidden, unavailable
from app.db.constants import AuditAction, ConnectionStatus, NotificationCategory, Severity
from app.db.models import Connection, DerivOAuthState, User
from app.providers.base import CredentialBundle, ProviderError
from app.providers.deriv import OAUTH_SENTINEL
from app.services import audit, deriv_sessions, notifications
from app.services import connections as connection_service
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

#: Every scope Deriv documents for third-party apps. Anything else is rejected here rather
#: than being sent and failing with ``invalid_scope`` at Deriv.
ALLOWED_SCOPES = {"trade", "account_manage", "application_read", "payment"}
#: Scopes VELTRANE must never request: payment unlocks withdrawal operations.
FORBIDDEN_SCOPES = {"payment"}


def utcnow() -> datetime:
    return datetime.now(UTC)


def configured() -> bool:
    return settings.deriv_oauth_configured


def requested_scopes() -> list[str]:
    scopes = [scope for scope in settings.deriv_oauth_scope_list if scope in ALLOWED_SCOPES]
    scopes = [scope for scope in scopes if scope not in FORBIDDEN_SCOPES]
    return scopes or ["trade"]


def _verifier() -> str:
    """43–128 character PKCE verifier from the unreserved set."""
    return secrets.token_urlsafe(64)[:96]


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _aad(state: str) -> str:
    return f"deriv_oauth_state:{state}"


def _purge_expired(db: Session, *, now: datetime) -> None:
    db.query(DerivOAuthState).filter(DerivOAuthState.expires_at < now - timedelta(hours=1)).delete(
        synchronize_session=False
    )


# --------------------------------------------------------------------------- start
def authorize_url(
    db: Session,
    *,
    user: User,
    purpose: str = "connect",
    connection_id: str = "",
    visitor_id: str = "",
) -> dict:
    """Create a single-use handshake and return the URL the browser must open."""
    if not configured():
        raise unavailable(
            "deriv_oauth_not_configured",
            "Deriv OAuth is not configured on this deployment. An administrator must register a "
            "Deriv application and set VELTRANE_DERIV_OAUTH_CLIENT_ID.",
        )
    now = utcnow()
    _purge_expired(db, now=now)
    state = secrets.token_urlsafe(32)
    verifier = _verifier()
    scopes = requested_scopes()
    redirect_uri = settings.deriv_oauth_redirect
    envelope = encrypt_json({"code_verifier": verifier}, aad=_aad(state))
    row = DerivOAuthState(
        state=state,
        org_id=user.org_id,
        user_id=user.id,
        purpose=purpose if purpose in {"connect", "reconnect"} else "connect",
        connection_id=connection_id or None,
        redirect_uri=redirect_uri,
        scopes=" ".join(scopes),
        verifier_envelope=envelope.as_json(),
        visitor_id=visitor_id or None,
        expires_at=now + timedelta(seconds=settings.deriv_oauth_state_ttl_seconds),
    )
    db.add(row)
    db.flush()
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.deriv_oauth_client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    return {
        "authorize_url": f"{settings.deriv_oauth_auth_url}?{query}",
        "state": state,
        "expires_at": row.expires_at.isoformat(),
        "scopes": scopes,
        "redirect_uri": redirect_uri,
    }


# --------------------------------------------------------------------------- callback
def _consume_state(db: Session, *, state: str, now: datetime) -> DerivOAuthState:
    row = db.query(DerivOAuthState).filter(DerivOAuthState.state == state).first()
    if row is None:
        raise bad_request("oauth_state_unknown", "This authorisation link is not recognised. Start again from Connect Deriv.")
    if row.consumed_at is not None:
        raise bad_request("oauth_state_used", "This authorisation link was already used. Start again from Connect Deriv.")
    expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if expires_at < now:
        raise bad_request("oauth_state_expired", "This authorisation link expired. Start again from Connect Deriv.")
    row.consumed_at = now
    db.flush()
    return row


def _exchange_code(*, code: str, verifier: str, redirect_uri: str) -> dict:
    try:
        response = httpx.post(
            settings.deriv_oauth_token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.deriv_oauth_client_id,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            timeout=25,
        )
    except httpx.HTTPError as exc:
        raise unavailable("deriv_oauth_unreachable", "Could not reach Deriv's token endpoint. Try again.") from exc

    if response.status_code >= 400:
        detail = ""
        try:
            payload = response.json() or {}
            detail = str(payload.get("error_description") or payload.get("error") or "")
        except ValueError:
            detail = response.text[:200]
        log.warning("deriv_oauth_exchange_failed", extra={"extra_fields": {"status": response.status_code}})
        raise bad_request(
            "deriv_oauth_rejected",
            "Deriv rejected the authorisation. It may have expired; start again from Connect Deriv.",
            {"provider_status": response.status_code, "provider_error": detail[:200]},
        )
    try:
        payload = response.json() or {}
    except ValueError as exc:
        raise bad_request("deriv_oauth_bad_response", "Deriv returned an unreadable token response.") from exc
    token = str(payload.get("access_token") or "")
    if not token:
        raise bad_request("deriv_oauth_no_token", "Deriv returned no access token.")
    try:
        expires_in = int(payload.get("expires_in") or 0)
    except (TypeError, ValueError):
        expires_in = 0
    return {
        "access_token": token,
        "token_type": str(payload.get("token_type") or "Bearer"),
        "expires_in": expires_in,
        "scopes": str(payload.get("scope") or ""),
    }


def _deriv_connection(db: Session, org_id: str) -> Connection | None:
    return (
        db.query(Connection)
        .filter(Connection.org_id == org_id, Connection.provider == "deriv")
        .order_by(Connection.created_at)
        .first()
    )


def complete(db: Session, *, state: str, code: str, user: User | None = None) -> dict:
    """Exchange an authorisation code and create or refresh the Deriv connection.

    ``user`` is passed when the caller is already authenticated; the callback route
    instead resolves the user from the stored state row.
    """
    now = utcnow()
    row = _consume_state(db, state=state, now=now)
    if user is not None and row.user_id != user.id:
        raise forbidden("oauth_state_owner_mismatch", "This authorisation belongs to a different account.")
    owner = user or db.get(User, row.user_id)
    if owner is None:
        raise bad_request("oauth_user_missing", "The account that started this authorisation no longer exists.")

    try:
        envelope = Envelope.from_json(row.verifier_envelope)
        verifier = str(decrypt_json(envelope, aad=_aad(state)).get("code_verifier") or "")
    except Exception as exc:  # noqa: BLE001 - unreadable state is a failed handshake, not a crash
        log.error("deriv_oauth_verifier_unreadable", extra={"extra_fields": {"state_id": row.id}})
        raise bad_request("oauth_state_corrupt", "The stored authorisation could not be read. Start again.") from exc
    if not verifier:
        raise bad_request("oauth_state_corrupt", "The stored authorisation could not be read. Start again.")

    tokens = _exchange_code(code=code, verifier=verifier, redirect_uri=row.redirect_uri)
    bundle = CredentialBundle(api_key=tokens["access_token"], app_id=OAUTH_SENTINEL)
    try:
        identity = deriv_sessions.adapter().test_connection(bundle)
    except ProviderError as exc:
        deriv_sessions.record_auth_event(
            db,
            connection=None,
            org_id=owner.org_id,
            event="oauth_connect_failed",
            outcome="failed",
            code=exc.code,
            message=exc.message,
        )
        raise bad_request(exc.code, exc.message) from exc

    expires_at = now + timedelta(seconds=tokens["expires_in"]) if tokens["expires_in"] else None
    oauth_meta = {
        "token_kind": "oauth",
        "expires_at": expires_at.isoformat() if expires_at else None,
        "scopes": tokens["scopes"] or " ".join(requested_scopes()),
        "connected_at": now.isoformat(),
        "client_id": settings.deriv_oauth_client_id,
    }

    connection = _deriv_connection(db, owner.org_id)
    created = connection is None
    if created:
        connection = Connection(
            org_id=owner.org_id,
            created_by=owner.id,
            kind="broker",
            provider="deriv",
            label="Deriv",
            environment="read_only",
            status=ConnectionStatus.PENDING,
            permissions={"read": True, "trade": False, "withdraw": False, "withdrawal_attestation": False},
            capabilities={},
        )
        db.add(connection)
        db.flush()
    elif connection.last_auth_error:
        connection.last_auth_error = None
        connection.last_auth_error_at = None

    connection_service.store_credentials(
        db,
        connection,
        CredentialBundle(
            api_key=tokens["access_token"],
            app_id=OAUTH_SENTINEL,
            account_id=identity.get("account_id") or "",
        ),
    )
    previous_account = connection.provider_account_id
    connection_service.apply_identity(connection, identity, requested_account_id=previous_account or "")
    connection.provider_meta = {
        **(connection.provider_meta or {}),
        "oauth": oauth_meta,
        "token_kind": "oauth",
        "accounts": identity.get("accounts") or [],
        "nickname": identity.get("nickname", ""),
        "one_account_policy": True,
    }
    connection.status = ConnectionStatus.CONNECTED
    connection.last_error = None
    connection.last_sync_at = now
    connection.permissions = {
        **(connection.permissions or {}),
        "read": True,
        "withdraw": False,
        "withdrawal_scope": "not_requested",
        "scopes": requested_scopes(),
    }

    audit.record(
        db,
        action=AuditAction.CONNECTION_CREATED if created else AuditAction.CONNECTION_RECONNECTED,
        org_id=owner.org_id,
        actor_user_id=owner.id,
        actor_email=owner.email,
        target_type="connection",
        target_id=connection.id,
        meta={"provider": "deriv", "method": "oauth", "accounts": len(identity.get("accounts") or [])},
    )
    notifications.notify(
        db,
        org_id=owner.org_id,
        user_id=owner.id,
        category=NotificationCategory.CONNECTION,
        title="Deriv connected",
        body=(
            f"Deriv authorisation complete with {len(identity.get('accounts') or [])} account(s) visible. "
            "Trading stays off until you enable it explicitly."
        ),
        severity=Severity.INFO,
    )
    return {
        "connection_id": connection.id,
        "created": created,
        "identity": {
            "nickname": identity.get("nickname", ""),
            "accounts": identity.get("accounts") or [],
            "account_id": connection.provider_account_id,
            "account_type": connection.provider_account_type,
            "currency": connection.provider_currency,
        },
        "oauth": oauth_meta,
    }


# --------------------------------------------------------------------------- account switch
def switch_account(db: Session, *, connection: Connection, account_id: str) -> dict:
    """Select which Deriv account type this one VELTRANE connection trades.

    Deriv exposes demo and real accounts under a single authorisation; switching only
    changes which one VELTRANE reads and trades. It never creates a second profile.
    """
    accounts = (connection.provider_meta or {}).get("accounts") or []
    chosen = next((row for row in accounts if str(row.get("account_id")) == str(account_id)), None)
    if chosen is None:
        raise bad_request("account_not_available", "That account is not visible to the current Deriv authorisation.")
    connection.provider_account_id = str(chosen.get("account_id"))
    connection.provider_account_type = str(chosen.get("account_type") or "real")
    connection.provider_currency = str(chosen.get("currency") or "USD")
    connection.environment = "paper" if connection.provider_account_type == "demo" else connection.environment
    db.flush()
    return {
        "account_id": connection.provider_account_id,
        "account_type": connection.provider_account_type,
        "currency": connection.provider_currency,
        "is_demo": connection.provider_account_type == "demo",
    }


def token_state(connection: Connection, *, now: datetime | None = None) -> dict:
    """Report token expiry without ever returning the token."""
    now = now or utcnow()
    oauth = (connection.provider_meta or {}).get("oauth") or {}
    raw = oauth.get("expires_at")
    if not raw:
        return {"kind": (connection.provider_meta or {}).get("token_kind") or "pat", "expires_at": None, "expired": False}
    try:
        expires_at = datetime.fromisoformat(str(raw))
    except ValueError:
        return {"kind": "oauth", "expires_at": None, "expired": False}
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return {
        "kind": "oauth",
        "expires_at": expires_at.isoformat(),
        "expired": expires_at <= now,
        "days_left": max(0, (expires_at - now).days),
    }


def require_single_connection(db: Session, *, user: User) -> Connection:
    connection = _deriv_connection(db, user.org_id)
    if connection is None:
        raise conflict("deriv_not_connected", "Connect Deriv before changing accounts.")
    return connection
