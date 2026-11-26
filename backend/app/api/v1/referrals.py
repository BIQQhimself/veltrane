"""Public referral entry point and per-user referral status.

``GET /referrals/deriv`` is the link that can be placed anywhere (site, email signature,
social profile): it records a click and redirects to Deriv. A browser following it never
needs a VELTRANE session, and no personal data is stored — only an opaque visitor id.
"""

from __future__ import annotations

from app.api.deps import get_current_user
from app.core import rate_limit as limit
from app.core.config import settings
from app.db.models import User
from app.db.session import get_db
from app.services import referrals
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

router = APIRouter(prefix="/referrals", tags=["referrals"])


class ClickRequest(BaseModel):
    visitor_id: str = Field(default="", max_length=64)
    landing: str = Field(default="", max_length=200)


@router.get("/deriv")
def deriv_redirect(
    request: Request,
    v: str = Query(default="", max_length=64),
    db: Session = Depends(get_db),
):
    """Record the click, then hand the visitor to Deriv's signup page."""
    limit.enforce(request, "referral_redirect", limit=30, window=3600)
    config = referrals.link_config(db)
    if not config["enabled"]:
        # No link configured: send the visitor to the product rather than a dead end.
        return RedirectResponse(f"{settings.web_base_url.rstrip('/')}/register", status_code=302)
    referrals.record_click(
        db,
        visitor_id=v,
        referrer=(request.headers.get("referer") or "")[:200],
        landing=str(request.url.path)[:200],
    )
    db.commit()
    return RedirectResponse(referrals.signup_url(config), status_code=302)


@router.post("/click")
def click(payload: ClickRequest, request: Request, db: Session = Depends(get_db)):
    """Browser-side click record, used by the in-app referral button."""
    limit.enforce(request, "referral_click", limit=20, window=3600)
    event = referrals.record_click(
        db, visitor_id=payload.visitor_id, referrer="app", landing=payload.landing or "deriv-signup"
    )
    db.commit()
    return {"status": "recorded", "event_id": event.id, "visitor_id": event.visitor_id}


@router.get("/me")
def my_referral_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The signed-in user's own referral journey. Partner revenue is not shown here."""
    return {
        "link": referrals.signup_url(referrals.link_config(db)),
        **referrals.summary_for_user(db, user),
        "note": "VELTRANE never pays you for your own referral; commissions are settled by Deriv.",
    }


@router.get("/config")
def public_config(db: Session = Depends(get_db)):
    """What the marketing page needs: the link and whether it is enabled."""
    config = referrals.link_config(db)
    return {"enabled": config["enabled"], "url": config["url"] if config["enabled"] else ""}
