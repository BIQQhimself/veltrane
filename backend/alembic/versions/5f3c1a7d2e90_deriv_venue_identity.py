"""deriv venue identity, provider auth events and auto-trade configuration

Revision ID: 5f3c1a7d2e90
Revises: 9b2e5c7a41d0
Create Date: 2026-11-26 10:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5f3c1a7d2e90"
down_revision: Union[str, None] = "9b2e5c7a41d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- venue identity on connections -------------------------------------------------
    op.add_column("connections", sa.Column("provider_account_id", sa.String(length=64), nullable=True))
    op.add_column("connections", sa.Column("provider_account_type", sa.String(length=16), nullable=True))
    op.add_column("connections", sa.Column("provider_currency", sa.String(length=16), nullable=True))
    op.add_column(
        "connections",
        sa.Column("provider_meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.add_column(
        "connections",
        sa.Column("session_state", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.add_column("connections", sa.Column("last_auth_error", sa.Text(), nullable=True))
    op.add_column(
        "connections", sa.Column("last_auth_error_at", sa.DateTime(timezone=True), nullable=True)
    )


    # ---- provider authentication events ------------------------------------------------
    op.create_table(
        "provider_auth_events",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "org_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "connection_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("connections.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("event", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_provider_auth_events_org_id", "provider_auth_events", ["org_id"])
    op.create_index("ix_provider_auth_events_connection_id", "provider_auth_events", ["connection_id"])
    op.create_index("ix_provider_auth_events_provider", "provider_auth_events", ["provider"])
    op.create_index("ix_provider_auth_events_event", "provider_auth_events", ["event"])
    op.create_index("ix_provider_auth_events_occurred_at", "provider_auth_events", ["occurred_at"])

    # ---- automation configuration ------------------------------------------------------
    op.create_table(
        "auto_trade_configs",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "org_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="approval"),
        sa.Column("symbol", sa.String(length=32), nullable=False, server_default="R_100"),
        sa.Column("contract_type", sa.String(length=24), nullable=False, server_default="CALL"),
        sa.Column("stake", sa.Numeric(20, 8), nullable=False, server_default="10"),
        sa.Column("duration", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("duration_unit", sa.String(length=4), nullable=False, server_default="t"),
        sa.Column("max_open_contracts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_stake_per_trade", sa.Numeric(20, 8), nullable=False, server_default="25"),
        sa.Column("daily_loss_limit", sa.Numeric(20, 8), nullable=False, server_default="100"),
        sa.Column("daily_stake_limit", sa.Numeric(20, 8), nullable=False, server_default="250"),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("signal_ttl_seconds", sa.Integer(), nullable=False, server_default="600"),
        sa.Column("created_by", sa.Uuid(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_signal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("halt_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("connection_id", name="uq_auto_trade_connection"),
    )
    op.create_index("ix_auto_trade_configs_org_id", "auto_trade_configs", ["org_id"])
    op.create_index("ix_auto_trade_configs_connection_id", "auto_trade_configs", ["connection_id"])

    op.create_table(
        "auto_trade_signals",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "org_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "config_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("auto_trade_configs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="approval"),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("contract_type", sa.String(length=24), nullable=False),
        sa.Column("stake", sa.Numeric(20, 8), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("duration_unit", sa.String(length=4), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("risk_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("order_id", sa.Uuid(as_uuid=False), sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contract_id", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.Uuid(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_auto_trade_signals_org_id", "auto_trade_signals", ["org_id"])
    op.create_index("ix_auto_trade_signals_connection_id", "auto_trade_signals", ["connection_id"])
    op.create_index("ix_auto_trade_signals_config_id", "auto_trade_signals", ["config_id"])
    op.create_index("ix_auto_trade_signals_status", "auto_trade_signals", ["status"])


def downgrade() -> None:
    op.drop_index("ix_auto_trade_signals_status", table_name="auto_trade_signals")
    op.drop_index("ix_auto_trade_signals_config_id", table_name="auto_trade_signals")
    op.drop_index("ix_auto_trade_signals_connection_id", table_name="auto_trade_signals")
    op.drop_index("ix_auto_trade_signals_org_id", table_name="auto_trade_signals")
    op.drop_table("auto_trade_signals")

    op.drop_index("ix_auto_trade_configs_connection_id", table_name="auto_trade_configs")
    op.drop_index("ix_auto_trade_configs_org_id", table_name="auto_trade_configs")
    op.drop_table("auto_trade_configs")

    op.drop_index("ix_provider_auth_events_occurred_at", table_name="provider_auth_events")
    op.drop_index("ix_provider_auth_events_event", table_name="provider_auth_events")
    op.drop_index("ix_provider_auth_events_provider", table_name="provider_auth_events")
    op.drop_index("ix_provider_auth_events_connection_id", table_name="provider_auth_events")
    op.drop_index("ix_provider_auth_events_org_id", table_name="provider_auth_events")
    op.drop_table("provider_auth_events")

    op.drop_column("connections", "last_auth_error_at")
    op.drop_column("connections", "last_auth_error")
    op.drop_column("connections", "session_state")
    op.drop_column("connections", "provider_meta")
    op.drop_column("connections", "provider_currency")
    op.drop_column("connections", "provider_account_type")
    op.drop_column("connections", "provider_account_id")
