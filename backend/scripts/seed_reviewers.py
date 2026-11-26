"""Create the two dedicated reviewer accounts on a demo instance. Idempotent.

    reviewer.admin@veltrane.dev   staff role `owner`   the command centre
    reviewer@veltrane.dev         Elite plan           the subscriber experience

Both accounts are demo-only. The script refuses to run when live trading is
enabled on the deployment, and it clears any live-trading permission it finds,
so a reviewer signing in can never reach a real venue. Market data is the
synthetic demo feed and every order the platform records is labelled simulated.

Usage:
    python -m scripts.seed_reviewers
    VELTRANE_REVIEWER_PASSWORD='...' python -m scripts.seed_reviewers
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.constants import PlanCode, StaffRole, UserStatus
from app.db.models import Plan, TradingPermission, User
from app.db.session import SessionLocal
from app.services import auth, billing

SPECS: list[tuple[str, str, str, str | None]] = [
    ("reviewer.admin@veltrane.dev", "Reviewer Inspector", PlanCode.ELITE, StaffRole.OWNER),
    ("reviewer@veltrane.dev", "Reviewer Subscriber", PlanCode.ELITE, None),
]

DEFAULT_PASSWORD = "Veltrane!Review2026"
TERMS_VERSION = "terms-2026-01"


def _ensure(db, email: str, name: str, plan_code: str, staff_role: str | None, password: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user, _ = auth.register(
            db,
            email=email,
            password=password,
            full_name=name,
            country="GB",
            terms_version=TERMS_VERSION,
            ip="127.0.0.1",
            user_agent="scripts.seed_reviewers",
        )
        action = "created"
    else:
        user.password_hash = auth.hash_password(password)
        action = "updated"

    user.status = UserStatus.ACTIVE
    user.email_verified_at = user.email_verified_at or datetime.now(UTC)
    user.is_staff = bool(staff_role)
    user.staff_role = staff_role
    db.flush()

    plan = db.get(Plan, plan_code)
    if plan is None:
        raise RuntimeError(f"plan {plan_code} is not seeded; run scripts.seed first")
    sub = billing.ensure_free_subscription(db, user.org_id)
    if sub.plan_code != plan_code or sub.status != "active":
        billing.activate_plan(
            db,
            org_id=user.org_id,
            plan_code=plan_code,
            provider="mock",
            provider_subscription_id=f"sub_review_{plan_code}_{user.org_id[:8]}",
            amount=float(plan.price_monthly),
            currency=plan.currency,
            event_id=f"seed-reviewers-{plan_code}-{user.org_id}",
            trial=False,
        )

    for permission in db.query(TradingPermission).filter(TradingPermission.org_id == user.org_id).all():
        permission.live_enabled = False
        permission.status = "revoked"
        permission.revoked_at = datetime.now(UTC)
        permission.revoked_reason = "Reviewer accounts are demo-only."

    print(f"{action:8} {email:28} {plan_code:6} {('staff:' + staff_role) if staff_role else ''}")
    return user


def main() -> None:
    if get_settings().live_trading_enabled:
        raise SystemExit("refusing to seed reviewer accounts: live trading is enabled on this deployment")

    password = os.environ.get("VELTRANE_REVIEWER_PASSWORD", DEFAULT_PASSWORD)
    errors = auth.password_strength_errors(password)
    if errors:
        raise SystemExit(f"reviewer password is too weak: {', '.join(errors)}")

    db = SessionLocal()
    try:
        for email, name, plan_code, staff_role in SPECS:
            _ensure(db, email, name, plan_code, staff_role, password)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"\nBoth reviewer accounts use the password: {password}")
    print("Live trading is disabled on this deployment; the accounts hold no live permission.")


if __name__ == "__main__":
    try:
        main()
    except AppError as exc:  # pragma: no cover
        print(f"Seeding failed: {exc.detail}", file=sys.stderr)
        raise SystemExit(1) from exc
