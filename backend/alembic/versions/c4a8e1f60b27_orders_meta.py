"""venue contract facts on orders

Revision ID: c4a8e1f60b27
Revises: 5f3c1a7d2e90
Create Date: 2026-11-26 11:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4a8e1f60b27"
down_revision: Union[str, None] = "5f3c1a7d2e90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )


def downgrade() -> None:
    op.drop_column("orders", "meta")
