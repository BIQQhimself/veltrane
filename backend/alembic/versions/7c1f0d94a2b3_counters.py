"""counters

Invoice numbering needs a counter that outlives the invoices it numbers.

Revision ID: 7c1f0d94a2b3
Revises: 06a853d2dfbc
Create Date: 2026-11-26 07:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7c1f0d94a2b3"
down_revision: Union[str, None] = "06a853d2dfbc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "counters",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_counters")),
    )
    # Continue after the highest number already issued this month so existing
    # invoices never collide with a fresh counter.
    op.execute(
        """
        INSERT INTO counters (key, value)
        SELECT 'invoice:' || split_part(replace(number, 'INV-', ''), '-', 1),
               max(CAST(right(number, 5) AS INTEGER))
        FROM invoices
        GROUP BY 1
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("counters")
