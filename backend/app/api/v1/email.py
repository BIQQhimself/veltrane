"""Email preferences, unsubscribe and the Resend webhook.

The webhook is the only unauthenticated route here, and it is authenticated by the Svix
signature Resend sends. An unsigned or stale request is rejected before any row is touched.
"""

from __future__ import annotations

import json
import logging

from app.api.deps import get_current_user
from app.core import rate_limit as limit
from app.core.config import settings
from app.core.errors import bad_request, unauthorized
from app.db.models import NotificationPreference, User
from app.db.session import get_db
from app.services import audit
from app.services import email as email_service
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

router = APIRouter(tags=["email"])


class PreferenceUpdate(BaseModel):
    email_enabled: bool | None = None
    digest_enabled: bool | None = None
    promotional: bool | None = None
    categories: dict[str, bool] | None = None


class UnsubscribeRequest(BaseModel):
    token: str = Field(min_length=8, max_length=64)


@router.get("/email/preferences")
def get_preferences(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pref = email_service.ensure_preferences(db, user)
    db.commit()
    return {
        "preferences": email_service.preferences_dict(pref),
        "provider": email_service.provider_name(),
        "delivery_configured": email_service.delivery_configured(),
        "categories": ["security", "billing", "risk", "connection", "trade", "order", "digest", "system"],
        "note": (
            "Security and billing notices cannot be switched off: they report actions on your account."
        ),
    }


@router.put("/email/preferences")
def update_preferences(
    payload: PreferenceUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pref = email_service.update_preferences(db, user, payload.model_dump(exclude_none=True))
    audit.record(
        db,
        action="email.preferences_updated",
        org_id=user.org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        meta={"email_enabled": pref.email_enabled, "digest_enabled": pref.digest_enabled, "promotional": pref.promotional},
    )
    db.commit()
    return {"preferences": email_service.preferences_dict(pref)}


@router.post("/email/unsubscribe")
def unsubscribe(payload: UnsubscribeRequest, request: Request, db: Session = Depends(get_db)):
    """Turn off promotional mail for a token. Transactional mail is unaffected."""
    limit.enforce(request, "email_unsubscribe", limit=20, window=3600)
    pref = email_service.unsubscribe_by_token(db, payload.token.strip())
    if pref is None:
        # Same answer either way: a valid-looking guess must not reveal which tokens exist.
        return {"status": "accepted"}
    audit.record(
        db,
        action="email.unsubscribed",
        org_id=pref.org_id,
        actor_user_id=pref.user_id,
        meta={"scope": "promotional"},
    )
    db.commit()
    return {"status": "unsubscribed", "scope": "promotional"}


@router.get("/email/unsubscribe")
def unsubscribe_preview(token: str = Query(min_length=8, max_length=64), db: Session = Depends(get_db)):
    """Read-only check so the page can show the right state before the user confirms."""
    pref = db.query(NotificationPreference).filter_by(unsubscribe_token=token.strip()).first()
    if pref is None:
        return {"valid": False, "promotional": False}
    return {"valid": True, "promotional": bool(pref.promotional)}


@router.post("/webhooks/resend")
async def resend_webhook(request: Request, db: Session = Depends(get_db)):
    """Delivery events from Resend, verified with the Svix signature scheme."""
    raw = await request.body()
    if len(raw) > 256 * 1024:
        raise bad_request("payload_too_large", "Webhook payload too large.")
    secret = settings.resend_webhook_secret
    if not secret:
        raise unauthorized("webhook_not_configured", "This deployment has no Resend webhook secret configured.")
    headers = {key: value for key, value in request.headers.items()}
    if not email_service.verify_svix_signature(secret=secret, headers=headers, payload=raw):
        log.warning("resend_webhook_signature_invalid")
        raise unauthorized("invalid_signature", "Webhook signature verification failed.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise bad_request("invalid_payload", "Webhook body is not JSON.") from exc
    event_type = str(payload.get("type") or "")
    result = email_service.handle_webhook(db, payload=payload, event_type=event_type)
    db.commit()
    return {"received": True, **result}
