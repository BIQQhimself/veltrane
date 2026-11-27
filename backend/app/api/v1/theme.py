"""Public visual identity: what the browser reads before it paints."""

from __future__ import annotations

from app.db.session import get_db
from app.services import theme as theme_service
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

router = APIRouter(tags=["theme"])


@router.get("/theme")
def get_theme(response: Response, db: Session = Depends(get_db)):
    """Unauthenticated on purpose: the sign-in page carries the same identity.

    Only colours and display strings are exposed — nothing tenant-specific.
    """
    response.headers["Cache-Control"] = "public, max-age=60"
    return theme_service.get_theme(db)


@router.get("/theme/tokens")
def get_tokens():
    return {"tokens": theme_service.tokens(), "branding_defaults": theme_service.DEFAULT_BRANDING}
