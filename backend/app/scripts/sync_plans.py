"""Push the plan catalog in ``app/services/entitlements.py`` to the database.

Startup only *creates* missing plans so administrator edits survive restarts. When the
catalog itself changes (a new limit, a new tier), run this deliberately:

    .venv/bin/python -m app.scripts.sync_plans            # report only
    .venv/bin/python -m app.scripts.sync_plans --apply    # write the catalog

Existing subscriptions keep their plan code; the limits they resolve against change.
"""

from __future__ import annotations

import sys

from app.db.models import Plan
from app.db.session import SessionLocal
from app.services import entitlements


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    with SessionLocal() as db:
        before = {plan.code: dict(plan.limits) for plan in db.query(Plan).all()}
        entitlements.sync_plans(db)

        for code, limits in before.items():
            plan = db.get(Plan, code)
            changed = {
                key: (limits.get(key), plan.limits.get(key))
                for key in set(limits) | set(plan.limits)
                if limits.get(key) != plan.limits.get(key)
            }
            if changed:
                print(f"{code}: {len(changed)} limit(s) differ")
                for key, (old, new) in sorted(changed.items()):
                    print(f"  {key}: {old!r} -> {new!r}")

        if apply:
            db.commit()
            print("catalog written")
        else:
            db.rollback()
            print("dry run: nothing written (pass --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
