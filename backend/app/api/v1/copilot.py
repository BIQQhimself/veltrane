from __future__ import annotations

from app.api.deps import get_current_user
from app.api.schemas import CopilotAnalyseRequest
from app.core.errors import bad_request
from app.core.rate_limit import enforce
from app.db.models import User
from app.services import copilot
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/copilot", tags=["copilot"])


@router.get("/briefing")
def briefing(request: Request, user: User = Depends(get_current_user)):
    enforce(request, "copilot", limit=30, window=60)
    return copilot.briefing()


@router.post("/analyse")
def analyse(payload: CopilotAnalyseRequest, request: Request, user: User = Depends(get_current_user)):
    enforce(request, "copilot", limit=60, window=60)
    try:
        return copilot.analyse(payload.symbol, payload.timeframe, payload.duration_seconds)
    except ValueError as exc:
        raise bad_request("analysis_unavailable", str(exc)) from exc
