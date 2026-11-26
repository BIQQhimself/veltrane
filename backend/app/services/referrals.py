"""Deriv referral programme: link resolution, funnel events and honest reporting.

What VELTRANE can observe itself is recorded as a funnel step (click, registration,
OAuth start, connection). What only Deriv can confirm — a referred client trading and
generating commission — is never invented: conversions stay ``estimated`` until an
operator records a verified figure, and the API labels them accordingly.
"""

from __future__ import annotations

import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from app.core.config import settings
from app.db.models import ReferralEvent, SystemSetting, User
from app.db.models.billing import Subscription
from sqlalchemy import func
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

SETTING_KEY = "referrals.deriv"
TRACKING_PARAMS = ("t", "affiliate_token", "sidi", "ca")
VISITOR_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# --------------------------------------------------------------------------- link config
def link_config(db: Session) -> dict:
    """Referral link, overridable by an administrator without a redeploy."""
    stored = db.get(SystemSetting, SETTING_KEY)
    value = (stored.value if stored else {}) or {}
    url = str(value.get("url") or settings.deriv_referral_url or "").strip()
    campaign = str(value.get("campaign") or "veltrane")
    return {
        "url": url,
        "campaign": campaign,
        "token": tracking_token(url) or settings.deriv_referral_token,
        "enabled": bool(value.get("enabled", True)) and bool(url),
        "updated_at": stored.updated_at.isoformat() if stored and stored.updated_at else None,
    }


def save_link_config(db: Session, *, url: str, campaign: str, enabled: bool, actor_id: str) -> SystemSetting:
    if url and not url.startswith("https://"):
        raise ValueError("The referral link must be an https URL.")
    if url and not tracking_token(url):
        raise ValueError("The referral link must carry a Deriv tracking parameter (t, affiliate_token, sidi or ca).")
    setting = db.get(SystemSetting, SETTING_KEY) or SystemSetting(key=SETTING_KEY, description="Deriv referral link")
    setting.value = {"url": url.strip(), "campaign": campaign.strip()[:40], "enabled": bool(enabled)}
    setting.updated_by = actor_id
    db.add(setting)
    db.flush()
    return setting


def tracking_token(url: str) -> str:
    if not url:
        return ""
    try:
        query = parse_qs(urlsplit(url).query)
    except ValueError:
        return ""
    for name in TRACKING_PARAMS:
        values = query.get(name)
        if values and values[0]:
            return values[0][:64]
    return ""


def signup_url(config: dict) -> str:
    """The link opened for people without a Deriv account.

    Kept as the plain referral link: Deriv's own signup page is the right place to collect
    identity documents, and the tracking token is what attributes the client.
    """
    if not config.get("enabled"):
        return ""
    parts = urlsplit(config["url"])
    query = parse_qs(parts.query)
    if config.get("campaign") and "utm_campaign" not in query:
        query["utm_campaign"] = [config["campaign"]]
        query.setdefault("utm_medium", ["affiliate"])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode({k: v[0] for k, v in query.items()}), parts.fragment))


# --------------------------------------------------------------------------- events
def record(
    db: Session,
    *,
    kind: str,
    visitor_id: str | None = None,
    user: User | None = None,
    connection_id: str | None = None,
    status: str = "estimated",
    meta: dict | None = None,
) -> ReferralEvent:
    event = ReferralEvent(
        kind=kind[:24],
        source="deriv",
        visitor_id=(visitor_id or "")[:64] or None,
        user_id=user.id if user else None,
        org_id=user.org_id if user else None,
        connection_id=connection_id,
        status=status[:16],
        meta=meta or {},
    )
    db.add(event)
    db.flush()
    return event


def valid_visitor(visitor_id: str | None) -> str:
    """Reject anything that is not an opaque client-generated id."""
    candidate = (visitor_id or "").strip()
    if VISITOR_RE.match(candidate):
        return candidate
    return ""


def record_click(db: Session, *, visitor_id: str = "", referrer: str = "", landing: str = "") -> ReferralEvent:
    """One click per visitor per day: a refresh is not a new referral."""
    visitor = valid_visitor(visitor_id) or f"anon-{secrets.token_urlsafe(9)}"
    since = utcnow() - timedelta(hours=12)
    existing = (
        db.query(ReferralEvent)
        .filter(
            ReferralEvent.kind == "click",
            ReferralEvent.visitor_id == visitor,
            ReferralEvent.created_at >= since,
        )
        .first()
    )
    if existing:
        return existing
    return record(
        db,
        kind="click",
        visitor_id=visitor,
        meta={"referrer": referrer[:200], "landing": landing[:200]},
    )


def attribute_registration(db: Session, *, user: User, visitor_id: str = "") -> ReferralEvent | None:
    """Link a new signup to the referral click that brought the visitor in."""
    visitor = valid_visitor(visitor_id)
    if not visitor:
        return None
    already = db.query(ReferralEvent).filter(ReferralEvent.user_id == user.id, ReferralEvent.kind == "registration").first()
    if already:
        return already
    click = (
        db.query(ReferralEvent)
        .filter(ReferralEvent.kind == "click", ReferralEvent.visitor_id == visitor)
        .order_by(ReferralEvent.created_at.desc())
        .first()
    )
    return record(
        db,
        kind="registration",
        visitor_id=visitor,
        user=user,
        meta={"attributed": bool(click), "click_at": click.created_at.isoformat() if click else None},
    )


def record_oauth_start(db: Session, *, user: User, visitor_id: str = "", purpose: str = "connect") -> None:
    record(db, kind="oauth_start", visitor_id=valid_visitor(visitor_id) or None, user=user, meta={"purpose": purpose})


def record_connection(db: Session, *, user: User, connection_id: str, visitor_id: str = "", accounts: int = 0) -> None:
    record(
        db,
        kind="connection",
        visitor_id=valid_visitor(visitor_id) or None,
        user=user,
        connection_id=connection_id,
        meta={"accounts": accounts},
    )


def record_conversion(db: Session, *, user_id: str, amount: float, currency: str = "USD", note: str = "") -> ReferralEvent:
    """An operator-confirmed commission line. Verified by definition: a human entered it."""
    user = db.get(User, user_id)
    return record(
        db,
        kind="conversion",
        user=user,
        status="verified",
        meta={"amount": round(float(amount), 2), "currency": currency[:8], "note": note[:200]},
    )


# --------------------------------------------------------------------------- reporting
def funnel(db: Session, *, days: int = 90) -> dict:
    since = utcnow() - timedelta(days=days)
    rows = (
        db.query(ReferralEvent.kind, ReferralEvent.status, func.count(ReferralEvent.id))
        .filter(ReferralEvent.created_at >= since)
        .group_by(ReferralEvent.kind, ReferralEvent.status)
        .all()
    )
    counts: dict[str, int] = {}
    for kind, _status, count in rows:
        counts[kind] = counts.get(kind, 0) + int(count)
    visitors = (
        db.query(func.count(func.distinct(ReferralEvent.visitor_id)))
        .filter(ReferralEvent.created_at >= since, ReferralEvent.kind == "click", ReferralEvent.visitor_id.isnot(None))
        .scalar()
        or 0
    )
    verified = (
        db.query(ReferralEvent)
        .filter(ReferralEvent.kind == "conversion", ReferralEvent.status == "verified", ReferralEvent.created_at >= since)
        .all()
    )
    verified_amount = sum(float((event.meta or {}).get("amount") or 0) for event in verified)
    clicks = counts.get("click", 0)
    registrations = counts.get("registration", 0)
    connections = counts.get("connection", 0)
    return {
        "window_days": days,
        "unique_visitors": int(visitors),
        "clicks": clicks,
        "registrations": registrations,
        "oauth_starts": counts.get("oauth_start", 0),
        "connections": connections,
        "verified_conversions": len(verified),
        "verified_commission": round(verified_amount, 2),
        "estimated_conversions": counts.get("conversion", 0) - len(verified),
        "click_to_registration": round(registrations / clicks, 4) if clicks else None,
        "registration_to_connection": round(connections / registrations, 4) if registrations else None,
        "note": (
            "Clicks, registrations and connections are observed by VELTRANE. Commission is only "
            "counted when an operator records a verified figure from the Deriv partner dashboard."
        ),
    }


def recent_events(db: Session, *, limit: int = 100) -> list[dict]:
    rows = db.query(ReferralEvent).order_by(ReferralEvent.created_at.desc()).limit(limit).all()
    return [
        {
            "id": row.id,
            "kind": row.kind,
            "status": row.status,
            "visitor_id": row.visitor_id,
            "user_id": row.user_id,
            "connection_id": row.connection_id,
            "meta": row.meta,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def summary_for_user(db: Session, user: User) -> dict:
    """What a subscriber sees about their own Deriv journey (no partner revenue)."""
    rows = (
        db.query(ReferralEvent)
        .filter(ReferralEvent.user_id == user.id)
        .order_by(ReferralEvent.created_at.desc())
        .limit(20)
        .all()
    )
    return {
        "events": [
            {"kind": row.kind, "created_at": row.created_at.isoformat() if row.created_at else None} for row in rows
        ]
    }


def plan_mix(db: Session) -> list[dict]:
    """Referred accounts by plan, for the admin referral view."""
    rows = (
        db.query(Subscription.plan_code, func.count(Subscription.id))
        .join(User, User.org_id == Subscription.org_id)
        .join(ReferralEvent, ReferralEvent.user_id == User.id)
        .filter(ReferralEvent.kind == "registration", Subscription.status.in_(("active", "trialing", "past_due")))
        .group_by(Subscription.plan_code)
        .all()
    )
    return [{"plan": plan, "accounts": int(count)} for plan, count in rows]
