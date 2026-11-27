"""tier limits: three paid tiers plus the free sandbox

The tier structure changed at the product level (Tier 1 = 600 trades/day, Tier 2 = 1,200,
Elite = no platform cap, live trading and the autonomous agent on every paid tier). Plan
rows are the server-side authority for entitlements, so an existing deployment needs the
stored values updated — a code change alone would leave the old limits in place.

Only the keys this change owns are touched; anything an administrator customised elsewhere
in the JSON is left exactly as it is.

Revision ID: 8f3c21d4b7a0
Revises: 5158360ba7ed
Create Date: 2026-11-27 12:40:00.000000

"""

import json
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "8f3c21d4b7a0"
down_revision: Union[str, None] = "5158360ba7ed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIER_CHANGES: dict[str, dict[str, Any]] = {
    "basic": {
        "name": "Basic",
        "tagline": "Live trading and an autonomous agent that works while the platform is open.",
        "features": [
            "Core AI strategy library",
            "Manual trading, demo or live after authorisation",
            "Autonomous agent while the platform is open (session mode)",
            "600 trades per day",
            "Essential analytics",
        ],
        "limits": {
            "max_daily_demo_executions": 600,
            "max_automated_trades_per_day": 600,
            "automation_mode": "session",
            "live_trading": True,
        },
    },
    "pro": {
        "name": "Pro",
        "tagline": "The agent keeps trading when you close the platform.",
        "features": [
            "Expanded strategy library",
            "Backtesting & walk-forward testing",
            "Strategy customisation",
            "Advanced analytics",
            "Autonomous trading that continues when you close the platform",
            "1,200 trades per day",
            "Eligible for live trading after explicit authorisation",
        ],
        "limits": {
            "max_daily_demo_executions": 1200,
            "max_automated_trades_per_day": 1200,
            "automation_mode": "background",
            "live_trading": True,
        },
    },
    "elite": {
        "limits": {
            "max_daily_demo_executions": 0,
            "max_automated_trades_per_day": 0,
            "automation_mode": "background",
            "live_trading": True,
        },
    },
}

PREVIOUS: dict[str, dict[str, Any]] = {
    "basic": {
        "name": "Basic",
        "tagline": "Core AI strategies and essential automation for a single trader.",
        "limits": {
            "max_daily_demo_executions": 50,
            "max_automated_trades_per_day": 40,
            "automation_mode": "session",
            "live_trading": True,
        },
    },
    "pro": {
        "name": "Pro",
        "tagline": "Expanded strategies, backtesting and advanced risk analytics.",
        "limits": {
            "max_daily_demo_executions": 250,
            "max_automated_trades_per_day": 250,
            "automation_mode": "background",
            "live_trading": True,
        },
    },
    "elite": {
        "limits": {
            "max_daily_demo_executions": 1000,
            "max_automated_trades_per_day": 0,
            "automation_mode": "background",
            "live_trading": True,
        },
    },
}


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _apply(changes: dict[str, dict[str, Any]]) -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT code, limits FROM plans")).fetchall()
    for code, limits in rows:
        change = changes.get(code)
        if not change:
            continue
        merged = _as_dict(limits)
        merged.update(change.get("limits") or {})
        bind.execute(
            sa.text("UPDATE plans SET name = :name, tagline = :tagline, limits = :limits WHERE code = :code"),
            {
                "code": code,
                "name": change.get("name") or code.title(),
                "tagline": change.get("tagline") or "",
                "limits": json.dumps(merged),
            },
        )
        if change.get("features"):
            bind.execute(
                sa.text("UPDATE plans SET features = :features WHERE code = :code"),
                {"code": code, "features": json.dumps(change["features"])},
            )


def upgrade() -> None:
    _apply(TIER_CHANGES)


def downgrade() -> None:
    _apply(PREVIOUS)
