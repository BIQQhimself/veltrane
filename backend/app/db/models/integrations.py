"""Models for OAuth handshakes, the referral programme and email operations.

Kept apart from the trading models: none of these rows can move money, and the email
tables are operational records rather than financial ones.
"""

from __future__ import annotations

from datetime import datetime

from app.db.base import Base, IdTimestampMixin
from app.db.types import JSONType
from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column


class DerivOAuthState(Base, IdTimestampMixin):
    """One pending authorisation handshake.

    The PKCE verifier is stored encrypted and bound to the state value, so a stolen
    database row alone cannot complete a code exchange. Rows are single-use.
    """

    __tablename__ = "deriv_oauth_states"

    state: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    org_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(16), default="connect", nullable=False)
    connection_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    redirect_uri: Mapped[str] = mapped_column(String(400), nullable=False)
    scopes: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    verifier_envelope: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    visitor_id: Mapped[str | None] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReferralEvent(Base, IdTimestampMixin):
    """A referral funnel step.

    ``status`` separates what we can observe (a click, a registration, a connection)
    from what only Deriv can confirm (a funded, trading conversion). Estimated rows are
    never presented as verified revenue.
    """

    __tablename__ = "referral_events"

    kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(24), default="deriv", nullable=False, index=True)
    visitor_id: Mapped[str | None] = mapped_column(String(64), index=True)
    user_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), index=True)
    org_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), index=True)
    connection_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    status: Mapped[str] = mapped_column(String(16), default="estimated", nullable=False)
    meta: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


class EmailCampaign(Base, IdTimestampMixin):
    """An admin-composed announcement, optionally scheduled and targeted."""

    __tablename__ = "email_campaigns"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    subject: Mapped[str] = mapped_column(String(240), nullable=False)
    template: Mapped[str] = mapped_column(String(64), default="announcement", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    audience: Mapped[str] = mapped_column(String(16), default="all", nullable=False)
    tier: Mapped[str | None] = mapped_column(String(24))
    group_name: Mapped[str | None] = mapped_column(String(40))
    test_email: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False, index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recipients: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    meta: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


class NotificationPreference(Base, IdTimestampMixin):
    """Per-user email choices, including the promotional unsubscribe state."""

    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("user_id", name="uq_notification_preferences_user_id"),)

    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    org_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    promotional: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    categories: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    unsubscribe_token: Mapped[str] = mapped_column(String(48), nullable=False, unique=True, index=True)
    last_digest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
