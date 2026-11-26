from __future__ import annotations

from datetime import UTC, timedelta

from app.api import serializers
from app.api.deps import get_current_user
from app.api.schemas import (
    ChangePasswordRequest,
    EmailOnlyRequest,
    LoginRequest,
    MfaDisableRequest,
    MfaEnableRequest,
    MfaLoginRequest,
    PasswordResetRequest,
    RegisterRequest,
    VerifyEmailRequest,
)
from app.core.config import settings
from app.core.errors import bad_request, unauthorized
from app.core.rate_limit import enforce
from app.core.security import create_token, decode_token, new_csrf_token
from app.db.models import User
from app.db.session import get_db
from app.services import auth as auth_service
from app.services import entitlements, platform_switch
from app.services.live_authorization import live_state
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "veltrane_refresh"
CSRF_COOKIE = "veltrane_csrf"


def _set_refresh_cookies(response: Response, refresh_token: str, csrf_token: str) -> None:
    max_age = settings.refresh_token_days * 24 * 3600
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/api/v1/auth",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _issue(response: Response, issued: dict, user: User) -> dict:
    csrf = new_csrf_token()
    _set_refresh_cookies(response, issued["refresh_token"], csrf)
    return {
        "access_token": issued["access_token"],
        "token_type": "bearer",
        "expires_at": issued["expires_at"].isoformat(),
        "refresh_expires_at": issued["refresh_expires_at"].isoformat(),
        "csrf_token": csrf,
        "user": serializers.user_dict(user),
    }


@router.post("/register", status_code=201)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    enforce(request, "register", limit=5, window=3600)
    user, debug_token = auth_service.register(
        db,
        email=str(payload.email),
        password=payload.password,
        full_name=payload.full_name,
        country=payload.country,
        terms_version=payload.terms_version,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    body = {
        "status": "registered",
        "message": "Account created. Check your email to verify your address.",
        "email_verified_required": settings.require_email_verification,
        "user": serializers.user_dict(user),
    }
    if debug_token:
        body["debug_verification_token"] = debug_token
        body["debug_notice"] = "Development only: this token is never returned in production."
    return body


@router.post("/verify-email")
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    user = auth_service.verify_email(db, token=payload.token)
    db.commit()
    return {"status": "verified", "user": serializers.user_dict(user)}


@router.post("/resend-verification")
def resend_verification(payload: EmailOnlyRequest, request: Request, db: Session = Depends(get_db)):
    enforce(request, "resend", limit=3, window=3600)
    token = auth_service.resend_verification(db, email=str(payload.email))
    db.commit()
    body = {"status": "queued", "message": "If that address needs verification, an email has been queued."}
    if token:
        body["debug_verification_token"] = token
    return body


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    enforce(request, "login", limit=10, window=300)
    user, mfa_required = auth_service.authenticate(
        db,
        email=str(payload.email),
        password=payload.password,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    if mfa_required:
        token, _, _ = create_token(
            subject=user.id,
            token_type="access",
            org_id=user.org_id,
            extra={"mfa_pending": True},
            expires_delta=timedelta(minutes=5),
        )
        db.commit()
        return {"mfa_required": True, "mfa_token": token}
    issued = auth_service.complete_login(
        db, user=user, ip=request.client.host if request.client else None, user_agent=request.headers.get("user-agent")
    )
    db.commit()
    return _issue(response, issued, user)


@router.post("/mfa/verify")
def verify_mfa_login(payload: MfaLoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    enforce(request, "mfa", limit=10, window=300)
    try:
        claims = decode_token(payload.mfa_token, expected_type="access")
    except ValueError:
        raise unauthorized("invalid_token", "MFA session expired. Sign in again.") from None
    if not claims.get("mfa_pending"):
        raise bad_request("invalid_token", "This token is not an MFA challenge.")
    user = db.get(User, claims["sub"])
    if user is None:
        raise unauthorized("invalid_token", "MFA session expired. Sign in again.")
    issued = auth_service.verify_mfa_login(
        db,
        user=user,
        code=payload.code,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return _issue(response, issued, user)


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    enforce(request, "refresh", limit=60, window=300)
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise unauthorized("no_session", "No active session.")
    csrf_cookie = request.cookies.get(CSRF_COOKIE)
    csrf_header = request.headers.get("x-csrf-token")
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        raise unauthorized("csrf_failed", "CSRF validation failed.")
    issued = auth_service.rotate_refresh(
        db,
        refresh_token=token,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    user = db.get(User, decode_token(issued["access_token"], expected_type="access")["sub"])
    db.commit()
    return _issue(response, issued, user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        auth_service.revoke_refresh(db, refresh_token=token)
        db.commit()
    authorization = request.headers.get("authorization") or ""
    if authorization.lower().startswith("bearer "):
        from datetime import datetime

        from app.core.security import decode_token, revoke_token_jti

        try:
            claims = decode_token(authorization.split(" ", 1)[1], expected_type="access")
            revoke_token_jti(claims["jti"], datetime.fromtimestamp(claims["exp"], tz=UTC))
        except (ValueError, KeyError):
            pass
    _clear_cookies(response)
    return {"status": "signed_out"}


@router.post("/logout-all")
def logout_all(response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = auth_service.logout_all(db, user)
    db.commit()
    _clear_cookies(response)
    return {"status": "signed_out", "sessions_revoked": count}


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.db.models import Organization
    from app.services.entitlements import active_subscription
    from app.services.usage import get_usage

    org = db.get(Organization, user.org_id)
    ent = entitlements.resolve_entitlements(db, user.org_id)
    sub = active_subscription(db, user.org_id)
    return {
        "user": serializers.user_dict(user),
        "organization": serializers.org_dict(org) if org else None,
        "entitlements": ent,
        "subscription": {
            "plan_code": sub.plan_code if sub else "free",
            "status": sub.status if sub else "active",
            "current_period_end": serializers.iso(sub.current_period_end) if sub else None,
            "cancel_at_period_end": sub.cancel_at_period_end if sub else False,
            "pending_plan_code": sub.pending_plan_code if sub else None,
        },
        "usage": {
            "demo_executions_today": int(get_usage(db, user.org_id, "demo_executions")),
            "backtests_today": int(get_usage(db, user.org_id, "backtests")),
        },
        "live": live_state(db, user.org_id),
        "platform": {
            "live_trading_enabled": platform_switch.effective(db),
            "demo_market_data_enabled": settings.demo_market_data_enabled,
            "env": settings.env,
        },
    }


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    auth_service.change_password(db, user=user, current=payload.current_password, new=payload.new_password)
    db.commit()
    _clear_cookies(response)
    return {"status": "password_changed", "message": "All sessions were signed out."}


@router.post("/mfa/setup")
def setup_mfa(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = auth_service.setup_mfa(db, user=user)
    db.commit()
    return {**result, "next": "Scan the URI, then POST /auth/mfa/enable with a 6-digit code."}


@router.post("/mfa/enable")
def enable_mfa(payload: MfaEnableRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    codes = auth_service.enable_mfa(db, user=user, code=payload.code)
    db.commit()
    return {"status": "enabled", "recovery_codes": codes, "notice": "Store these codes offline. They are shown once."}


@router.post("/mfa/disable")
def disable_mfa(payload: MfaDisableRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    auth_service.disable_mfa(db, user=user, password=payload.password)
    db.commit()
    return {"status": "disabled"}


@router.post("/password/forgot")
def forgot_password(payload: EmailOnlyRequest, request: Request, db: Session = Depends(get_db)):
    enforce(request, "forgot", limit=5, window=3600)
    token = auth_service.request_password_reset(db, email=str(payload.email))
    db.commit()
    body = {"status": "queued", "message": "If an account exists, a reset email has been queued."}
    if token:
        body["debug_reset_token"] = token
    return body


@router.post("/password/reset")
def reset_password(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    auth_service.reset_password(db, token=payload.token, new_password=payload.new_password)
    db.commit()
    return {"status": "password_reset", "message": "Sign in with your new password."}
