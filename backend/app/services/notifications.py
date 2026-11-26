from __future__ import annotations

import logging

from app.db.constants import Severity
from app.db.models import Notification, User
from app.services import email as email_service
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# The set of categories that may produce an email lives in the email service, so the two
# modules cannot drift apart.
EMAIL_CATEGORIES = email_service.IMMEDIATE_CATEGORIES

EMAIL_TEMPLATES = {
    "trade.opened": "A position was opened",
    "trade.closed": "A position was closed",
    "order.rejected": "An order was rejected by the risk engine",
    "order.failed": "An order failed to execute",
    "risk.limit": "A risk limit was reached",
    "connection.error": "An account connection needs attention",
    "billing.payment_failed": "A payment failed",
    "billing.renewal": "Your subscription renews soon",
    "security.mfa": "Two-factor authentication changed",
    "security.login": "New sign-in to your account",
    "system.maintenance": "Scheduled maintenance",
}


def notify(
    db: Session,
    *,
    org_id: str,
    category: str,
    title: str,
    body: str = "",
    severity: str = Severity.INFO,
    user_id: str | None = None,
    data: dict | None = None,
    email: bool = False,
) -> Notification:
    """Create an in-app notification.

    Callers must only invoke this after the underlying state change is committed or
    flushed, so a notification never claims an event that did not happen.
    """
    note = Notification(
        org_id=org_id,
        user_id=user_id,
        category=category,
        severity=severity,
        title=title[:160],
        body=body,
        data=data or {},
    )
    db.add(note)
    db.flush()

    if email or category in EMAIL_CATEGORIES:
        if user_id:
            users = [db.get(User, user_id)]
        else:
            users = db.query(User).filter(User.org_id == org_id, User.status == "active").all()
        for user in users:
            if user is None:
                continue
            # Per-user preferences decide; trading categories stay in-app and the digest.
            email_service.queue_for_notification(db, note=note, user=user)
    return note


def unread_count(db: Session, org_id: str) -> int:
    return db.query(Notification).filter(Notification.org_id == org_id, Notification.read_at.is_(None)).count()
