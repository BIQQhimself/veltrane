from __future__ import annotations

from datetime import datetime, timezone

from app.api import serializers
from app.api.deps import get_current_user, get_or_404
from app.api.schemas import OnboardingUpdate, ProfileUpdate, RiskProfileUpdate, SupportTicketCreate
from app.core.errors import not_found
from app.db.models import AuditLog, Notification, Organization, SupportTicket, User
from app.db.session import get_db
from app.services import notifications as notification_service
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

router = APIRouter(tags=["notifications"])


@router.get("/notifications")
def list_notifications(
    unread_only: bool = False,
    category: str | None = None,
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Notification).filter(Notification.org_id == user.org_id)
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))
    if category:
        query = query.filter(Notification.category == category)
    rows = query.order_by(Notification.created_at.desc()).limit(limit).all()
    return {
        "notifications": [
            {
                "id": n.id,
                "category": n.category,
                "severity": n.severity,
                "title": n.title,
                "body": n.body,
                "data": n.data,
                "read_at": serializers.iso(n.read_at),
                "created_at": serializers.iso(n.created_at),
            }
            for n in rows
        ],
        "unread_count": notification_service.unread_count(db, user.org_id),
    }


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    note = get_or_404(db, Notification, notification_id)
    if note is None or note.org_id != user.org_id:
        raise not_found("notification_not_found", "Notification not found.")
    if note.read_at is None:
        note.read_at = datetime.now(timezone.utc)
        db.commit()
    return {"status": "read"}


@router.post("/notifications/read-all")
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = (
        db.query(Notification)
        .filter(Notification.org_id == user.org_id, Notification.read_at.is_(None))
        .update({Notification.read_at: datetime.now(timezone.utc)})
    )
    db.commit()
    return {"status": "read", "count": count}


@router.get("/users/me/audit")
def my_audit(limit: int = Query(default=50, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.org_id == user.org_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "entries": [
            {
                "id": a.id,
                "action": a.action,
                "target_type": a.target_type,
                "target_id": a.target_id,
                "ip": a.ip,
                "meta": a.meta,
                "created_at": serializers.iso(a.created_at),
            }
            for a in rows
        ]
    }


@router.patch("/users/me")
def update_profile(payload: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.full_name:
        user.full_name = payload.full_name
    if payload.timezone:
        user.preferences = {**(user.preferences or {}), "timezone": payload.timezone}
    if payload.country:
        user.preferences = {**(user.preferences or {}), "country": payload.country.upper()[:2]}
    if payload.marketing_opt_in is not None:
        user.preferences = {**(user.preferences or {}), "marketing_opt_in": payload.marketing_opt_in}
    db.commit()
    return {"user": serializers.user_dict(user)}


@router.post("/users/me/onboarding")
def update_onboarding(payload: OnboardingUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.onboarding_step = max(user.onboarding_step, payload.step)
    org = db.get(Organization, user.org_id)
    if org is not None:
        org.onboarding = {
            **(org.onboarding or {}),
            **payload.data,
            "last_step_at": datetime.now(timezone.utc).isoformat(),
            "last_step": user.onboarding_step,
        }
    db.commit()
    return {"onboarding_step": user.onboarding_step, "onboarding": (org.onboarding if org else {})}


@router.put("/users/me/risk-profile")
def update_risk_profile(payload: RiskProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.risk_profile = payload.model_dump()
    db.commit()
    return {"risk_profile": user.risk_profile}


@router.post("/support/tickets", status_code=201)
def create_ticket(payload: SupportTicketCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ticket = SupportTicket(
        org_id=user.org_id,
        user_id=user.id,
        subject=payload.subject,
        body=payload.body,
        priority=payload.priority,
        status="open",
        messages=[{"role": "user", "message": payload.body, "at": datetime.now(timezone.utc).isoformat()}],
    )
    db.add(ticket)
    db.commit()
    return {"id": ticket.id, "status": ticket.status, "priority": ticket.priority}


@router.get("/support/tickets")
def list_tickets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(SupportTicket)
        .filter(SupportTicket.org_id == user.org_id)
        .order_by(SupportTicket.created_at.desc())
        .limit(50)
        .all()
    )
    return {
        "tickets": [
            {
                "id": t.id,
                "subject": t.subject,
                "status": t.status,
                "priority": t.priority,
                "messages": t.messages,
                "created_at": serializers.iso(t.created_at),
            }
            for t in rows
        ]
    }
