"""Seed reference data. Idempotent; safe to run repeatedly.

Usage:
    python -m scripts.seed                # plans, strategies, flags, risk policy
    VELTRANE_ADMIN_PASSWORD=... python -m scripts.seed   # also create/refresh the staff owner
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Base, FeatureFlag, Organization, RiskPolicy, SystemSetting, User
from app.db.session import SessionLocal, engine
from app.risk.types import DEFAULT_RISK_RULES
from app.services import analytics, auth, billing, entitlements, performance_fees, strategy_service

FLAGS = [
    ("live_trading_ui", False, "Show live-trading surfaces. Execution still requires the platform flag."),
    ("portfolio_optimization", False, "Portfolio optimiser module (not implemented in this build)."),
    ("ai_strategy_generation", False, "LLM strategy generation. Deterministic library only for now."),
    ("performance_fees", False, "Elite performance fee agreements. Requires legal review."),
    ("support_chat", False, "Live support chat. Ticket workflow is available instead."),
]


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        entitlements.seed_plans(db)
        strategy_service.seed_system_strategies(db)

        for key, enabled, description in FLAGS:
            if db.get(FeatureFlag, key) is None:
                db.add(FeatureFlag(key=key, enabled=enabled, description=description))

        if db.query(RiskPolicy).filter(RiskPolicy.org_id.is_(None)).count() == 0:
            db.add(
                RiskPolicy(
                    org_id=None,
                    name="global",
                    version=1,
                    rules=dict(DEFAULT_RISK_RULES),
                    is_active=True,
                )
            )

        if db.get(SystemSetting, analytics.COST_SETTING_KEY) is None:
            db.add(
                SystemSetting(
                    key=analytics.COST_SETTING_KEY,
                    value=dict(analytics.DEFAULT_COSTS),
                    description="Operator-provided cost inputs for contribution margin",
                )
            )
        if db.get(SystemSetting, performance_fees.SETTING_KEY) is None:
            db.add(
                SystemSetting(
                    key=performance_fees.SETTING_KEY,
                    value=dict(performance_fees.DEFAULT_SETTINGS),
                    description="Elite performance fee configuration (disabled by default)",
                )
            )

        admin_email = settings.admin_email.strip().lower()
        admin_password = settings.admin_password or os.environ.get("VELTRANE_ADMIN_PASSWORD", "")
        if admin_email and admin_password:
            user = db.query(User).filter(User.email == admin_email).first()
            if user is None:
                org = Organization(
                    name="VELTRANE Operations",
                    slug=f"veltrane-ops-{datetime.now(UTC).strftime('%Y%m%d')}",
                    timezone="UTC",
                )
                db.add(org)
                db.flush()
                user = User(
                    org_id=org.id,
                    email=admin_email,
                    password_hash=auth.hash_password(admin_password),
                    full_name="VELTRANE Operator",
                    status="active",
                    email_verified_at=datetime.now(UTC),
                    is_staff=True,
                    staff_role="owner",
                    terms_accepted_at=datetime.now(UTC),
                    terms_version="terms-2026-01",
                )
                db.add(user)
                db.flush()
                billing.ensure_free_subscription(db, org.id)
                print(f"Created staff owner {admin_email}")
            else:
                user.is_staff = True
                user.staff_role = user.staff_role or "owner"
                # Re-seeding must leave a working login. Without this a rotated
                # VELTRANE_ADMIN_PASSWORD silently stops matching the stored hash.
                user.password_hash = auth.hash_password(admin_password)
                print(f"Staff owner already exists: {admin_email} (password reset from env)")

        db.commit()
        print("Seed complete: plans, strategies, flags, risk policy, settings.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    try:
        seed()
    except AppError as exc:  # pragma: no cover
        print(f"Seed failed: {exc.detail}", file=sys.stderr)
        raise SystemExit(1) from exc
