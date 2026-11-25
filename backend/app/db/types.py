from __future__ import annotations

from sqlalchemy import JSON, Numeric
from sqlalchemy.dialects.postgresql import JSONB

# JSONB on PostgreSQL, portable JSON elsewhere (used by the SQLite-free test suite).
JSONType = JSON().with_variant(JSONB, "postgresql")
MoneyType = Numeric(24, 8)
QtyType = Numeric(28, 10)
