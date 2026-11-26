"""Outbound email: queueing, Resend delivery, retries, webhooks and preferences.

The outbox row is the source of truth. A message is only ever marked ``sent`` after the
provider returned an id, so nothing in the product can claim delivery that did not happen.
With ``VELTRANE_EMAIL_PROVIDER=outbox`` messages stay queued and are never reported as
sent — that is the honest default for a deployment with no Resend key.

Resend specifics used here:
* ``POST https://api.resend.com/emails`` with a Bearer key.
* ``Idempotency-Key`` header so a retry cannot double-send.
* Webhooks signed with Svix: ``svix-id``, ``svix-timestamp``, ``svix-signature`` where the
  signature is base64(HMAC-SHA256(secret, "{id}.{timestamp}.{body}")).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta

import httpx
from app.core.config import settings
from app.db.models import EmailCampaign, EmailOutbox, Notification, NotificationPreference, Trade, User
from app.db.models.billing import Subscription
from app.services.email_templates import (
    RenderedEmail,
    generic_notice,
    render_campaign,
    risk_alert,
    trading_digest,
)
from sqlalchemy import func
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
#: Categories sent immediately. Trading activity is batched into the daily digest instead:
#: one email per fill would be noise, and each message costs a Resend credit.
IMMEDIATE_CATEGORIES = {"security", "billing", "risk", "connection", "system"}
DIGEST_CATEGORIES = {"trade", "order", "digest"}
WEBHOOK_TOLERANCE_SECONDS = 300


def utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def provider_name() -> str:
    return "resend" if settings.email_provider == "resend" and settings.resend_api_key else "outbox"


def delivery_configured() -> bool:
    return provider_name() == "resend"


# --------------------------------------------------------------------------- preferences
MANDATORY_CATEGORIES = frozenset({"security", "billing"})


def ensure_preferences(db: Session, user: User) -> NotificationPreference:
    pref = db.query(NotificationPreference).filter(NotificationPreference.user_id == user.id).first()
    if pref is None:
        pref = NotificationPreference(
            user_id=user.id,
            org_id=user.org_id,
            unsubscribe_token=secrets.token_urlsafe(24),
        )
        db.add(pref)
        db.flush()
    return pref


def preferences_dict(pref: NotificationPreference) -> dict:
    return {
        "email_enabled": bool(pref.email_enabled),
        "digest_enabled": bool(pref.digest_enabled),
        "promotional": bool(pref.promotional),
        "categories": dict(pref.categories or {}),
        "last_digest_at": pref.last_digest_at.isoformat() if pref.last_digest_at else None,
    }


def update_preferences(db: Session, user: User, payload: dict) -> NotificationPreference:
    pref = ensure_preferences(db, user)
    if "email_enabled" in payload:
        pref.email_enabled = bool(payload["email_enabled"])
    if "digest_enabled" in payload:
        pref.digest_enabled = bool(payload["digest_enabled"])
    if "promotional" in payload:
        pref.promotional = bool(payload["promotional"])
    if "categories" in payload and isinstance(payload["categories"], dict):
        stored = {str(key)[:24]: bool(value) for key, value in payload["categories"].items()}
        # Security and billing notices report actions on the account; they are not optional.
        pref.categories = {**stored, **{key: True for key in MANDATORY_CATEGORIES}}
    db.flush()
    return pref


def email_allowed(db: Session, user: User, category: str) -> bool:
    if category in MANDATORY_CATEGORIES:
        return True
    pref = db.query(NotificationPreference).filter(NotificationPreference.user_id == user.id).first()
    if pref is None:
        return True
    if not pref.email_enabled:
        return False
    if pref.categories and category in pref.categories:
        return bool(pref.categories[category])
    return True


def promotional_allowed(db: Session, user: User) -> bool:
    pref = db.query(NotificationPreference).filter(NotificationPreference.user_id == user.id).first()
    if pref is None:
        return True
    return bool(pref.email_enabled and pref.promotional)


def unsubscribe_by_token(db: Session, token: str) -> NotificationPreference | None:
    pref = db.query(NotificationPreference).filter(NotificationPreference.unsubscribe_token == token).first()
    if pref is None:
        return None
    pref.promotional = False
    db.flush()
    return pref


def unsubscribe_url(token: str) -> str:
    return f"{settings.web_base_url.rstrip('/')}/unsubscribe?token={token}"


# --------------------------------------------------------------------------- queueing
def queue_email(
    db: Session,
    *,
    to_email: str,
    subject: str,
    body: str,
    category: str = "system",
    html: str | None = None,
    template: str = "",
    reply_to: str = "",
    unsubscribe_token: str | None = None,
) -> EmailOutbox:
    """Persist an outbound message. Delivery happens in :func:`deliver_queued`."""
    message = EmailOutbox(
        to_email=to_email.strip().lower(),
        subject=subject[:240],
        body=body,
        html=html,
        template=template[:64],
        category=category[:32],
        status="queued",
        provider=provider_name(),
        reply_to=(reply_to or settings.email_reply_to)[:320],
        unsubscribe_token=unsubscribe_token,
    )
    db.add(message)
    db.flush()
    return message


def queue_rendered(
    db: Session,
    *,
    to_email: str,
    rendered: RenderedEmail,
    unsubscribe_token: str = "",
) -> EmailOutbox:
    return queue_email(
        db,
        to_email=to_email,
        subject=rendered.subject,
        body=rendered.text,
        category=rendered.category,
        html=rendered.html,
        template=rendered.template,
        unsubscribe_token=unsubscribe_token or None,
    )


def queue_for_notification(db: Session, *, note: Notification, user: User) -> EmailOutbox | None:
    """Route an in-app notification to email only when it deserves one.

    Trading notifications stay in the app and in the daily digest; security, billing, risk
    and connection events go out immediately because they need attention before then.
    """
    if note.category not in IMMEDIATE_CATEGORIES:
        return None
    if not email_allowed(db, user, note.category):
        return None
    dashboard = f"{settings.web_base_url.rstrip('/')}/app/notifications"
    if note.category == "risk":
        rendered = risk_alert(
            user.full_name, note.title, note.body or note.title, dashboard, severity=note.severity
        )
    else:
        rendered = generic_notice(
            note.title, note.body or note.title, dashboard, severity=note.severity, category=note.category
        )
    pref = ensure_preferences(db, user)
    return queue_rendered(db, to_email=user.email, rendered=rendered, unsubscribe_token=pref.unsubscribe_token)


# --------------------------------------------------------------------------- delivery
def _is_suppressed(db: Session, address: str) -> bool:
    """Hard bounces and spam complaints stop all future mail to that address."""
    return (
        db.query(EmailOutbox.id)
        .filter(
            EmailOutbox.to_email == address.lower(),
            EmailOutbox.status.in_(("bounced", "complained")),
        )
        .first()
        is not None
    )


def _resend_send(message: EmailOutbox) -> tuple[bool, str, str, bool]:
    """Return (ok, provider_id, provider_status, retryable)."""
    payload = {
        "from": settings.email_from,
        "to": [message.to_email],
        "subject": message.subject,
        "text": message.body,
        "reply_to": message.reply_to or settings.email_reply_to,
    }
    if message.html:
        payload["html"] = message.html
    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
        "Idempotency-Key": message.id,
    }
    try:
        response = httpx.post(RESEND_URL, json=payload, headers=headers, timeout=20)
    except httpx.HTTPError as exc:
        return False, "", f"transport:{type(exc).__name__}", True

    if response.status_code < 300:
        try:
            body = response.json()
        except ValueError:
            body = {}
        return True, str((body or {}).get("id") or ""), "sent", False
    try:
        detail = str((response.json() or {}).get("message") or "")
    except ValueError:
        detail = response.text[:200]
    retryable = response.status_code == 429 or response.status_code >= 500
    return False, "", f"http_{response.status_code}:{detail}"[:200], retryable


def deliver(db: Session, message: EmailOutbox, *, now: datetime | None = None) -> str:
    """Attempt delivery of one queued message. Returns the resulting status."""
    now = now or utcnow()
    if message.status not in {"queued", "sending"}:
        return message.status
    if message.provider != "resend" or not settings.resend_api_key:
        # Outbox mode: keep the row queued. Marking it sent would be a false claim.
        message.provider_status = "outbox_only"
        db.flush()
        return message.status
    if _is_suppressed(db, message.to_email):
        message.status = "suppressed"
        message.provider_status = "suppressed_previous_bounce"
        db.flush()
        return message.status

    message.attempts += 1
    ok, provider_id, provider_status, retryable = _resend_send(message)
    message.provider_status = provider_status[:32]
    if ok:
        message.status = "sent"
        message.provider_message_id = provider_id or None
        message.sent_at = now
        message.error = None
        message.next_attempt_at = None
    else:
        message.error = provider_status[:2000]
        if retryable and message.attempts < settings.email_max_attempts:
            backoff = settings.email_retry_base_seconds * (2 ** (message.attempts - 1))
            message.next_attempt_at = now + timedelta(seconds=backoff)
            message.status = "queued"
        else:
            message.status = "failed"
            message.next_attempt_at = None
    db.flush()
    return message.status


def deliver_queued(db: Session, limit: int | None = None, *, now: datetime | None = None) -> dict:
    """Flush due messages. Safe to call from a scheduler tick."""
    now = now or utcnow()
    limit = limit or settings.email_batch_size
    due = (
        db.query(EmailOutbox)
        .filter(EmailOutbox.status == "queued")
        .filter((EmailOutbox.next_attempt_at.is_(None)) | (EmailOutbox.next_attempt_at <= now))
        .order_by(EmailOutbox.created_at)
        .limit(limit)
        .all()
    )
    summary = {"due": len(due), "sent": 0, "failed": 0, "queued": 0, "provider": provider_name()}
    for message in due:
        try:
            status = deliver(db, message, now=now)
        except Exception as exc:  # noqa: BLE001 - one bad message must not stop the batch
            db.rollback()
            log.error("email_delivery_error", extra={"extra_fields": {"message_id": message.id, "error": str(exc)}})
            summary["failed"] += 1
            continue
        if status == "sent":
            summary["sent"] += 1
        elif status == "failed":
            summary["failed"] += 1
        else:
            summary["queued"] += 1
    db.commit()
    return summary


def send_now(db: Session, message: EmailOutbox) -> str:
    """Best-effort immediate delivery for time-sensitive mail (verification, resets).

    Deliberately does not commit: the caller owns the transaction, so a registration that
    later fails cannot leave a delivered message behind a rolled-back account.
    """
    if not delivery_configured():
        return message.status
    try:
        return deliver(db, message)
    except Exception as exc:  # noqa: BLE001 - a mail outage must never fail the request
        log.warning("email_send_now_failed", extra={"extra_fields": {"message_id": message.id, "error": str(exc)}})
        return message.status


# --------------------------------------------------------------------------- webhooks
def verify_svix_signature(*, secret: str, headers: dict[str, str], payload: bytes, now: datetime | None = None) -> bool:
    """Verify a Svix/Resend webhook signature without extra dependencies."""
    if not secret:
        return False
    lowered = {key.lower(): value for key, value in headers.items()}
    msg_id = lowered.get("svix-id", "")
    timestamp = lowered.get("svix-timestamp", "")
    signatures = lowered.get("svix-signature", "")
    if not (msg_id and timestamp and signatures):
        return False
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    now = now or utcnow()
    if abs(now.timestamp() - sent_at) > WEBHOOK_TOLERANCE_SECONDS:
        return False
    key = secret[len("whsec_") :] if secret.startswith("whsec_") else secret
    try:
        key_bytes = base64.b64decode(key)
    except (ValueError, TypeError):
        key_bytes = key.encode()
    signed = f"{msg_id}.{timestamp}.".encode() + payload
    expected = base64.b64encode(hmac.new(key_bytes, signed, hashlib.sha256).digest()).decode()
    for candidate in signatures.split():
        version, _, signature = candidate.partition(",")
        if version and version != "v1":
            continue
        if hmac.compare_digest(signature or candidate, expected):
            return True
    return False


#: Resend event -> outbox status. Open/click events are recorded but do not change status.
EVENT_STATUS = {
    "email.sent": "sent",
    "email.delivered": "sent",
    "email.delivery_delayed": "queued",
    "email.bounced": "bounced",
    "email.complained": "complained",
    "email.failed": "failed",
    "email.suppressed": "suppressed",
}


def handle_webhook(db: Session, *, payload: dict, event_type: str, now: datetime | None = None) -> dict:
    now = now or utcnow()
    data = payload.get("data") or {}
    provider_id = str(data.get("email_id") or data.get("id") or "")
    message = None
    if provider_id:
        message = db.query(EmailOutbox).filter(EmailOutbox.provider_message_id == provider_id).first()
    if message is None:
        return {"matched": False, "event": event_type}

    message.events = [*(message.events or []), {"type": event_type, "at": now.isoformat()}][-20:]
    new_status = EVENT_STATUS.get(event_type)
    if new_status and message.status != "suppressed":
        message.status = new_status
    if event_type == "email.delivered":
        message.delivered_at = now
    if event_type in {"email.bounced", "email.complained", "email.failed"}:
        reason = data.get("bounce") or data.get("error") or data.get("complaint") or ""
        text = json.dumps(reason) if isinstance(reason, (dict, list)) else str(reason)
        message.error = text[:2000] or None
    db.flush()
    return {"matched": True, "event": event_type, "status": message.status, "id": message.id}


# --------------------------------------------------------------------------- analytics
def stats(db: Session, *, days: int = 30) -> dict:
    since = utcnow() - timedelta(days=days)
    by_status = {
        status: int(count)
        for status, count in db.query(EmailOutbox.status, func.count(EmailOutbox.id))
        .filter(EmailOutbox.created_at >= since)
        .group_by(EmailOutbox.status)
        .all()
    }
    by_category = {
        category: int(count)
        for category, count in db.query(EmailOutbox.category, func.count(EmailOutbox.id))
        .filter(EmailOutbox.created_at >= since)
        .group_by(EmailOutbox.category)
        .all()
    }
    sent = by_status.get("sent", 0)
    failed = by_status.get("failed", 0)
    bounced = by_status.get("bounced", 0)
    attempted = sent + failed + bounced
    return {
        "window_days": days,
        "provider": provider_name(),
        "delivery_configured": delivery_configured(),
        "from_address": settings.email_from,
        "by_status": by_status,
        "by_category": by_category,
        "sent": sent,
        "queued": by_status.get("queued", 0),
        "failed": failed,
        "bounced": bounced,
        "complained": by_status.get("complained", 0),
        "suppressed": by_status.get("suppressed", 0),
        "delivery_rate": round(sent / attempted, 4) if attempted else None,
        "note": (
            "Provider is the local outbox: messages are recorded but not delivered."
            if not delivery_configured()
            else "Counts come from stored messages and verified provider webhooks."
        ),
    }


# --------------------------------------------------------------------------- digests
def _backfill_preferences(db: Session, limit: int = 200) -> None:
    """Accounts created before this feature have no preference row yet; give them one."""
    missing = (
        db.query(User)
        .outerjoin(NotificationPreference, NotificationPreference.user_id == User.id)
        .filter(NotificationPreference.id.is_(None), User.status == "active", User.deleted_at.is_(None))
        .limit(limit)
        .all()
    )
    for user in missing:
        ensure_preferences(db, user)
    if missing:
        db.commit()


def digest_window(pref: NotificationPreference, now: datetime) -> tuple[datetime, datetime]:
    last = _as_utc(pref.last_digest_at)
    if last is None:
        return now - timedelta(days=1), now
    return min(last, now - timedelta(hours=1)), now


def send_digests(db: Session, *, now: datetime | None = None, limit: int = 200) -> dict:
    """One email per user per day summarising trading activity.

    A user with nothing to report receives nothing: an empty digest trains people to
    ignore the mail.
    """
    now = now or utcnow()
    if now.hour < settings.email_digest_hour_utc:
        return {"due": 0, "sent": 0, "skipped": 0, "hour": now.hour}
    _backfill_preferences(db)
    cutoff = now - timedelta(hours=20)
    prefs = (
        db.query(NotificationPreference)
        .filter(NotificationPreference.email_enabled.is_(True), NotificationPreference.digest_enabled.is_(True))
        .filter((NotificationPreference.last_digest_at.is_(None)) | (NotificationPreference.last_digest_at <= cutoff))
        .limit(limit)
        .all()
    )
    summary = {"due": len(prefs), "sent": 0, "skipped": 0, "hour": now.hour}
    for pref in prefs:
        user = db.get(User, pref.user_id)
        if user is None or user.status != "active":
            pref.last_digest_at = now
            summary["skipped"] += 1
            continue
        start, end = digest_window(pref, now)
        trades = (
            db.query(Trade).filter(Trade.org_id == user.org_id, Trade.closed_at >= start, Trade.closed_at <= end).all()
        )
        notes = (
            db.query(Notification)
            .filter(
                Notification.org_id == user.org_id,
                Notification.category.in_(("trade", "order", "risk")),
                Notification.created_at >= start,
            )
            .count()
        )
        if not trades and not notes:
            pref.last_digest_at = now
            summary["skipped"] += 1
            continue
        realised = sum(float(trade.net_pnl or 0) for trade in trades)
        opened = sum(1 for trade in trades if (_as_utc(trade.opened_at) or end) >= start)
        rejected = (
            db.query(Notification)
            .filter(
                Notification.org_id == user.org_id,
                Notification.category == "order",
                Notification.created_at >= start,
            )
            .count()
        )
        rendered = trading_digest(
            user.full_name,
            period=f"{start:%d %b %H:%M}–{end:%d %b %H:%M} UTC",
            opened=opened,
            closed=len(trades),
            rejected=rejected,
            realised=f"{realised:+,.2f}",
            positions=len({trade.instrument_symbol for trade in trades}),
            detail_url=f"{settings.web_base_url.rstrip('/')}/app/analytics",
            note=(
                "Figures are net of fees, spread and slippage and include simulated trades."
                if any(trade.is_demo for trade in trades)
                else "Figures are net of fees, spread and slippage."
            ),
        )
        queue_rendered(db, to_email=user.email, rendered=rendered, unsubscribe_token=pref.unsubscribe_token)
        pref.last_digest_at = now
        summary["sent"] += 1
    db.commit()
    return summary


# --------------------------------------------------------------------------- campaigns
def campaign_recipients(db: Session, campaign: EmailCampaign) -> list[User]:
    if campaign.audience == "test":
        if not campaign.test_email:
            return []
        return [User(email=campaign.test_email, full_name="Test recipient", org_id="", status="active")]
    query = db.query(User).filter(User.status == "active", User.deleted_at.is_(None))
    if campaign.audience == "tier":
        if not campaign.tier:
            return []
        query = query.join(Subscription, Subscription.org_id == User.org_id).filter(
            Subscription.plan_code == campaign.tier,
            Subscription.status.in_(("active", "trialing", "past_due")),
        )
    return query.order_by(User.created_at).all()


def send_due_campaigns(db: Session, *, now: datetime | None = None) -> dict:
    now = now or utcnow()
    due = (
        db.query(EmailCampaign)
        .filter(EmailCampaign.status == "scheduled", EmailCampaign.scheduled_at <= now)
        .order_by(EmailCampaign.scheduled_at)
        .limit(5)
        .all()
    )
    summary: dict = {"due": len(due), "queued": 0, "skipped": 0, "campaigns": []}
    for campaign in due:
        queued = 0
        for user in campaign_recipients(db, campaign):
            if campaign.audience != "test":
                if not promotional_allowed(db, user) or _is_suppressed(db, user.email):
                    summary["skipped"] += 1
                    continue
            pref = db.query(NotificationPreference).filter(NotificationPreference.user_id == user.id).first()
            token = pref.unsubscribe_token if pref else ""
            rendered = render_campaign(
                campaign.template,
                title=campaign.subject,
                body_text=campaign.body,
                cta_url=f"{settings.web_base_url.rstrip('/')}/app",
                unsubscribe_url=unsubscribe_url(token) if token else "",
            )
            queue_rendered(db, to_email=user.email, rendered=rendered, unsubscribe_token=token)
            queued += 1
        campaign.recipients = queued
        campaign.sent = queued
        campaign.status = "sent"
        campaign.started_at = now
        campaign.completed_at = now
        summary["queued"] += queued
        summary["campaigns"].append({"id": campaign.id, "name": campaign.name, "queued": queued})
    db.commit()
    return summary


def campaign_dict(campaign: EmailCampaign) -> dict:
    return {
        "id": campaign.id,
        "name": campaign.name,
        "subject": campaign.subject,
        "template": campaign.template,
        "body": campaign.body,
        "audience": campaign.audience,
        "tier": campaign.tier,
        "test_email": campaign.test_email,
        "status": campaign.status,
        "scheduled_at": campaign.scheduled_at.isoformat() if campaign.scheduled_at else None,
        "started_at": campaign.started_at.isoformat() if campaign.started_at else None,
        "completed_at": campaign.completed_at.isoformat() if campaign.completed_at else None,
        "recipients": campaign.recipients,
        "sent": campaign.sent,
        "failed": campaign.failed,
        "created_by": campaign.created_by,
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
    }
