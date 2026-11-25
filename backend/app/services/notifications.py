from __future__ import annotations

import logging

from app.db.constants import NotificationCategory, Severity
from app.db.models import Notification, User
from app.services.email import queue_email
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

EMAIL_CATEGORIES = {
    NotificationCategory.SECURITY,
    NotificationCategory.BILLING,
    NotificationCategory.RISK,
}

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
        recipients = []
        if user_id:
            user = db.get(User, user_id)
            if user:
                recipients = [user.email]
        else:
            recipients = [
                email_addr
                for (email_addr,) in db.query(User.email)
                .filter(User.org_id == org_id, User.status == "active")
                .all()
            ]
        for address in recipients:
            queue_email(db, to_email=address, subject=title, body=body, category=category)
    return note


def unread_count(db: Session, org_id: str) -> int:
    return (
        db.query(Notification)
        .filter(Notification.org_id == org_id, Notification.read_at.is_(None))
        .count()
    )
