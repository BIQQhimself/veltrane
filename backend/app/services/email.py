from __future__ import annotations

import logging

from app.db.models import EmailOutbox
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def queue_email(db: Session, *, to_email: str, subject: str, body: str, category: str = "system") -> EmailOutbox:
    """Persist an outbound email.

    Development and tests inspect this outbox instead of sending mail. A production
    deployment wires an SMTP/API provider into ``deliver_queued`` below.
    """
    email = EmailOutbox(to_email=to_email, subject=subject[:240], body=body, category=category, status="queued")
    db.add(email)
    db.flush()
    return email


def deliver_queued(db: Session, limit: int = 50) -> int:
    """Placeholder delivery worker.

    Returns the number of messages left queued because no provider is configured.
    Deliberately does not mark messages as sent: claiming delivery that did not happen
    would be a false operational statement.
    """
    pending = (
        db.query(EmailOutbox).filter(EmailOutbox.status == "queued").order_by(EmailOutbox.created_at).limit(limit).all()
    )
    if pending:
        log.info("email_outbox_pending", extra={"extra_fields": {"count": len(pending)}})
    return len(pending)
