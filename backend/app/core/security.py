from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
import pyotp
from app.core.config import settings
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
ALGORITHM = "HS256"

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, ValueError):
        return True


PASSWORD_MIN_LENGTH = 12
PASSWORD_SYMBOLS = "!@#$%^&*()-_=+[]{};:,.<>?/~`"


def password_strength_errors(password: str) -> list[str]:
    errors = []
    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"at least {PASSWORD_MIN_LENGTH} characters")
    if not any(c.islower() for c in password):
        errors.append("a lowercase letter")
    if not any(c.isupper() for c in password):
        errors.append("an uppercase letter")
    if not any(c.isdigit() for c in password):
        errors.append("a number")
    if not any(c in PASSWORD_SYMBOLS for c in password):
        errors.append("a symbol")
    return errors


def password_policy() -> dict:
    """Public description of the rules above, so the UI cannot advertise a weaker policy."""
    return {
        "min_length": PASSWORD_MIN_LENGTH,
        "requires": ["lowercase", "uppercase", "number", "symbol"],
    }


def _now() -> datetime:
    return datetime.now(UTC)


def create_token(
    *,
    subject: str,
    token_type: TokenType,
    org_id: str | None = None,
    role: str = "member",
    extra: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, str, datetime]:
    """Return (token, jti, expires_at)."""
    jti = uuid.uuid4().hex
    if expires_delta is None:
        expires_delta = (
            timedelta(minutes=settings.access_token_minutes)
            if token_type == "access"
            else timedelta(days=settings.refresh_token_days)
        )
    expires_at = _now() + expires_delta
    payload: dict[str, Any] = {
        "sub": subject,
        "typ": token_type,
        "jti": jti,
        "iat": int(_now().timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": "veltrane",
    }
    if org_id:
        payload["org"] = org_id
    if token_type == "access":
        payload["role"] = role
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
    return token, jti, expires_at


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub", "jti", "typ"]},
            issuer="veltrane",
        )
    except jwt.PyJWTError as exc:
        raise ValueError("invalid_token") from exc
    if payload.get("typ") != expected_type:
        raise ValueError("wrong_token_type")
    return payload


def revoke_token_jti(jti: str, expires_at: datetime) -> None:
    """Denylist a single access token until it would have expired anyway."""
    from app.core.redis_client import cache_set

    ttl = max(1, int((expires_at - _now()).total_seconds()))
    cache_set(f"revoked:jti:{jti}", "1", ttl)


def is_token_revoked(jti: str) -> bool:
    from app.core.redis_client import cache_get

    return cache_get(f"revoked:jti:{jti}") is not None


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


# ------------------------- MFA (TOTP) -------------------------


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, account_email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account_email, issuer_name=settings.mfa_issuer)


def verify_totp(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    return pyotp.TOTP(secret).verify(code.strip().replace(" ", ""), valid_window=1)


def generate_recovery_codes(count: int = 8) -> list[str]:
    return [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}" for _ in range(count)]


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()
