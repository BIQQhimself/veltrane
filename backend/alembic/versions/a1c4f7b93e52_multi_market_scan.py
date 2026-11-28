"""multi-market scan: universe and sector cap on automation configs

Revision ID: a1c4f7b93e52
Revises: 8f3c21d4b7a0
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1c4f7b93e52"
down_revision = "8f3c21d4b7a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auto_trade_configs", sa.Column("universe", sa.JSON(), nullable=True))
    op.add_column(
        "auto_trade_configs",
        sa.Column("sector_cap", sa.Integer(), nullable=False, server_default="2"),
    )


def downgrade() -> None:
    op.drop_column("auto_trade_configs", "sector_cap")
    op.drop_column("auto_trade_configs", "universe")
