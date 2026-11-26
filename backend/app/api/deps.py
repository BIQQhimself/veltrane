from __future__ import annotations

from collections.abc import Callable

from app.core.config import settings
from app.core.errors import forbidden, not_found, unauthorized
from app.core.security import decode_token
from app.db.constants import StaffRole, UserStatus
from app.db.models import User
from app.db.session import get_db
from fastapi import Depends, Request
from sqlalchemy.orm import Session


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header.split(" ", 1)[1].strip()
    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = bearer_token(request)
    if not token:
        raise unauthorized()
    try:
        payload = decode_token(token, expected_type="access")
    except ValueError:
        raise unauthorized("invalid_token", "Your session is invalid or has expired.") from None
    if payload.get("mfa_pending"):
        raise unauthorized("mfa_required", "Complete two-factor verification.")
    from app.core.security import is_token_revoked

    if payload.get("jti") and is_token_revoked(payload["jti"]):
        raise unauthorized("session_revoked", "This session has been signed out.")
    user = db.get(User, payload.get("sub"))
    if user is None or user.status in (UserStatus.SUSPENDED, UserStatus.DELETED):
        raise unauthorized("account_unavailable", "This account is not available.")
    if payload.get("org") and payload["org"] != user.org_id:
        raise unauthorized("invalid_token", "Session does not match this account.")
    if int(payload.get("ver") or 0) != int(user.token_version or 1):
        raise unauthorized("session_revoked", "This session has been revoked. Sign in again.")
    return user


def get_or_404(db: Session, model, value, *, code: str = "not_found", message: str = "Resource not found"):
    """Look up a UUID-keyed row, mapping malformed identifiers to a clean 404."""
    import uuid as _uuid

    try:
        _uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise not_found(code, message) from None
    obj = db.get(model, value)
    if obj is None:
        raise not_found(code, message)
    return obj


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    if not bearer_token(request):
        return None
    try:
        return get_current_user(request, db)
    except Exception:  # noqa: BLE001
        return None


def require_staff(*roles: str) -> Callable:
    allowed = set(roles) if roles else set(StaffRole.ALL)

    def dependency(user: User = Depends(get_current_user)) -> User:
        if not user.is_staff or user.staff_role not in allowed:
            # 404 avoids confirming the existence of the admin surface.
            from app.core.errors import not_found

            raise not_found()
        return user

    return dependency


require_admin = require_staff(StaffRole.OWNER, StaffRole.ADMIN)
require_analyst = require_staff(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ANALYST)
require_support = require_staff(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.SUPPORT)


def require_live_platform_flag() -> None:
    if not settings.live_trading_enabled:
        raise forbidden(
            "live_trading_disabled",
            "Live trading is disabled on this deployment. Paper trading is fully available.",
        )


def assert_same_org(user: User, org_id: str) -> None:
    if user.org_id != org_id:
        from app.core.errors import not_found

        raise not_found()
