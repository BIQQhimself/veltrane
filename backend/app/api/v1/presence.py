"""Presence and automation state for the signed-in tenant.

The workspace posts a heartbeat while it is visible. Session-bound automation (Tier 1) is
gated on that heartbeat, so closing the platform stops it without the client asking.
"""

from __future__ import annotations

from app.api.deps import get_current_user
from app.core.rate_limit import enforce
from app.db.models import User
from app.db.session import get_db
from app.services import automation_limits, presence
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

router = APIRouter(prefix="/presence", tags=["presence"])


@router.post("/heartbeat")
def heartbeat(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce(request, "presence", limit=240, window=60)
    seen = presence.touch(user.org_id)
    return {"presence": seen, "automation": automation_limits.state(db, user.org_id)}


@router.get("")
def state(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {
        "presence": presence.last_seen(user.org_id),
        "automation": automation_limits.state(db, user.org_id),
    }


@router.delete("")
def leave(user: User = Depends(get_current_user)):
    """Explicit goodbye. The key expires anyway; this just stops session automation sooner."""
    presence.clear(user.org_id)
    return {"status": "signed_out_of_presence"}
