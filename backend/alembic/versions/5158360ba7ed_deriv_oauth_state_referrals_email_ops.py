"""deriv oauth state, referrals and email operations

Adds the tables behind Deriv OAuth (single-use PKCE state), the referral funnel, the
admin email centre and per-user notification preferences, and extends ``email_outbox``
with what a real provider needs (HTML part, retries, provider status).

Revision ID: 5158360ba7ed
Revises: b7d2e5a91c34
Create Date: 2026-11-26 22:29:39.186943

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5158360ba7ed"
down_revision: Union[str, None] = "b7d2e5a91c34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "deriv_oauth_states",
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("purpose", sa.String(length=16), server_default="connect", nullable=False),
        sa.Column("connection_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("redirect_uri", sa.String(length=400), nullable=False),
        sa.Column("scopes", sa.String(length=160), server_default="", nullable=False),
        sa.Column("verifier_envelope", JSON, server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("visitor_id", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deriv_oauth_states")),
    )
    op.create_index(op.f("ix_deriv_oauth_states_org_id"), "deriv_oauth_states", ["org_id"], unique=False)
    op.create_index(op.f("ix_deriv_oauth_states_state"), "deriv_oauth_states", ["state"], unique=True)
    op.create_index(op.f("ix_deriv_oauth_states_user_id"), "deriv_oauth_states", ["user_id"], unique=False)
    op.create_index(op.f("ix_deriv_oauth_states_visitor_id"), "deriv_oauth_states", ["visitor_id"], unique=False)

    op.create_table(
        "email_campaigns",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("subject", sa.String(length=240), nullable=False),
        sa.Column("template", sa.String(length=64), server_default="announcement", nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("audience", sa.String(length=16), server_default="all", nullable=False),
        sa.Column("tier", sa.String(length=24), nullable=True),
        sa.Column("group_name", sa.String(length=40), nullable=True),
        sa.Column("test_email", sa.String(length=320), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recipients", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sent", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("meta", JSON, server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_campaigns")),
    )
    op.create_index(op.f("ix_email_campaigns_scheduled_at"), "email_campaigns", ["scheduled_at"], unique=False)
    op.create_index(op.f("ix_email_campaigns_status"), "email_campaigns", ["status"], unique=False)

    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("org_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("email_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("digest_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("promotional", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("categories", JSON, server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("unsubscribe_token", sa.String(length=48), nullable=False),
        sa.Column("last_digest_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_preferences")),
        sa.UniqueConstraint("user_id", name="uq_notification_preferences_user_id"),
    )
    op.create_index(
        op.f("ix_notification_preferences_org_id"), "notification_preferences", ["org_id"], unique=False
    )
    op.create_index(
        op.f("ix_notification_preferences_unsubscribe_token"),
        "notification_preferences",
        ["unsubscribe_token"],
        unique=True,
    )
    op.create_index(
        op.f("ix_notification_preferences_user_id"), "notification_preferences", ["user_id"], unique=False
    )

    op.create_table(
        "referral_events",
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("source", sa.String(length=24), server_default="deriv", nullable=False),
        sa.Column("visitor_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("org_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("connection_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="estimated", nullable=False),
        sa.Column("meta", JSON, server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_referral_events")),
    )
    op.create_index(op.f("ix_referral_events_kind"), "referral_events", ["kind"], unique=False)
    op.create_index(op.f("ix_referral_events_org_id"), "referral_events", ["org_id"], unique=False)
    op.create_index(op.f("ix_referral_events_source"), "referral_events", ["source"], unique=False)
    op.create_index(op.f("ix_referral_events_user_id"), "referral_events", ["user_id"], unique=False)
    op.create_index(op.f("ix_referral_events_visitor_id"), "referral_events", ["visitor_id"], unique=False)

    # Existing rows predate HTML delivery: defaults keep them readable and honest.
    op.add_column("email_outbox", sa.Column("html", sa.Text(), nullable=True))
    op.add_column("email_outbox", sa.Column("template", sa.String(length=64), server_default="", nullable=False))
    op.add_column(
        "email_outbox", sa.Column("provider", sa.String(length=16), server_default="outbox", nullable=False)
    )
    op.add_column(
        "email_outbox", sa.Column("provider_status", sa.String(length=32), server_default="", nullable=False)
    )
    op.add_column("email_outbox", sa.Column("reply_to", sa.String(length=320), server_default="", nullable=False))
    op.add_column("email_outbox", sa.Column("unsubscribe_token", sa.String(length=48), nullable=True))
    op.add_column("email_outbox", sa.Column("attempts", sa.Integer(), server_default="0", nullable=False))
    op.add_column("email_outbox", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("email_outbox", sa.Column("events", JSON, server_default=sa.text("'[]'::json"), nullable=False))
    op.add_column("email_outbox", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_email_outbox_category"), "email_outbox", ["category"], unique=False)
    op.create_index(op.f("ix_email_outbox_status"), "email_outbox", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_email_outbox_status"), table_name="email_outbox")
    op.drop_index(op.f("ix_email_outbox_category"), table_name="email_outbox")
    for column in (
        "delivered_at",
        "events",
        "next_attempt_at",
        "attempts",
        "unsubscribe_token",
        "reply_to",
        "provider_status",
        "provider",
        "template",
        "html",
    ):
        op.drop_column("email_outbox", column)
    op.drop_table("referral_events")
    op.drop_table("notification_preferences")
    op.drop_table("email_campaigns")
    op.drop_table("deriv_oauth_states")
