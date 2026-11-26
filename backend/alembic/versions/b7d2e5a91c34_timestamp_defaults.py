"""Give the Deriv tables the timestamp server defaults the models declare.

``5f3c1a7d2e90`` created ``provider_auth_events``, ``auto_trade_configs`` and
``auto_trade_signals`` with bare NOT NULL timestamps. The ORM omits ``created_at``/``updated_at``
from its INSERTs because the models declare a server default, so every session event, autotrade
config write and autotrade signal insert raised a NOT NULL violation on a migrated database.
Databases built from the models (the test suite) never saw it. Reproduced by
``tests/test_migrations.py``.

Revision ID: b7d2e5a91c34
Revises: c4a8e1f60b27
Create Date: 2026-11-26
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d2e5a91c34"
down_revision: Union[str, None] = "c4a8e1f60b27"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

TABLES = ("provider_auth_events", "auto_trade_configs", "auto_trade_signals")


def upgrade() -> None:
    for table in TABLES:
        op.alter_column(
            table, "created_at", server_default=sa.text("now()"), existing_type=sa.DateTime(timezone=True)
        )
        op.alter_column(
            table, "updated_at", server_default=sa.text("now()"), existing_type=sa.DateTime(timezone=True)
        )


def downgrade() -> None:
    for table in TABLES:
        op.alter_column(table, "created_at", server_default=None, existing_type=sa.DateTime(timezone=True))
        op.alter_column(table, "updated_at", server_default=None, existing_type=sa.DateTime(timezone=True))
