"""Create review accounts for a shared test instance. Idempotent.

Usage:
    python -m scripts.seed_testers
    VELTRANE_TESTER_PASSWORD='...' python -m scripts.seed_testers

Every account gets a verified email, accepted terms and a subscription on the
plan named in SPECS. Paid plans are activated through the same `activate_plan`
path the billing webhook uses, so invoices, payments and entitlements are real
records rather than hand-written rows.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

from app.core.errors import AppError
from app.db.constants import PlanCode, UserStatus
from app.db.models import Plan, User
from app.db.session import SessionLocal
from app.services import auth, billing

# (email, display name, plan, staff role)
# The domain must be routable-looking: `.test`, `.example`, `.invalid` and
# `localhost` are reserved and rejected by the email validator at login.
SPECS: list[tuple[str, str, str, str | None]] = [
    ("free@veltrane.dev", "Fiona Free", PlanCode.FREE, None),
    ("basic@veltrane.dev", "Bram Basic", PlanCode.BASIC, None),
    ("pro@veltrane.dev", "Priya Pro", PlanCode.PRO, None),
    ("elite@veltrane.dev", "Elias Elite", PlanCode.ELITE, None),
    ("analyst@veltrane.dev", "Ada Analyst", PlanCode.ELITE, "analyst"),
]

DEFAULT_PASSWORD = "Veltrane!Test2026"
TERMS_VERSION = "terms-2026-01"


def _ensure(db, email: str, name: str, plan_code: str, staff_role: str | None, password: str) -> User:
    if not email or "@" not in email:
        raise RuntimeError(f"refusing to seed an account with an invalid address: {email!r}")
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
            user_agent="scripts.seed_testers",
        )
        action = "created"
    else:
        # Re-running must leave a working login, not a stale hash.
        user.password_hash = auth.hash_password(password)
        action = "updated"

    user.status = UserStatus.ACTIVE
    user.email_verified_at = user.email_verified_at or datetime.now(UTC)
    if staff_role:
        user.is_staff = True
        user.staff_role = staff_role
    db.flush()

    if plan_code != PlanCode.FREE:
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
                provider_subscription_id=f"sub_seed_{plan_code}_{user.org_id[:8]}",
                amount=float(plan.price_monthly),
                currency=plan.currency,
                event_id=f"seed-testers-{plan_code}-{user.org_id}",
                trial=False,
            )
    else:
        billing.ensure_free_subscription(db, user.org_id)

    print(f"{action:8} {email:26} {plan_code:6} {'staff:' + staff_role if staff_role else ''}")
    return user


def main() -> None:
    password = os.environ.get("VELTRANE_TESTER_PASSWORD", DEFAULT_PASSWORD)
    errors = auth.password_strength_errors(password)
    if errors:
        raise SystemExit(f"tester password is too weak: {', '.join(errors)}")

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
    print(f"\nAll review accounts use the password: {password}")


if __name__ == "__main__":
    try:
        main()
    except AppError as exc:  # pragma: no cover
        print(f"Seeding failed: {exc.detail}", file=sys.stderr)
        raise SystemExit(1) from exc
