"""link binary contracts to their settled trade

Revision ID: 9b2e5c7a41d0
Revises: 7c1f0d94a2b3
Create Date: 2026-11-26 07:45:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9b2e5c7a41d0"
down_revision: Union[str, None] = "7c1f0d94a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("binary_contracts", sa.Column("trade_id", sa.Uuid(as_uuid=False), nullable=True))
    op.create_index("ix_binary_contracts_trade_id", "binary_contracts", ["trade_id"])
    op.create_foreign_key(
        "fk_binary_contracts_trade_id_trades",
        "binary_contracts",
        "trades",
        ["trade_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_binary_contracts_trade_id_trades", "binary_contracts", type_="foreignkey")
    op.drop_index("ix_binary_contracts_trade_id", table_name="binary_contracts")
    op.drop_column("binary_contracts", "trade_id")
