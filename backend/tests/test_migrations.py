"""Schema parity between ``alembic upgrade head`` and the ORM models.

Every other test builds its schema with ``Base.metadata.create_all``, which is derived from the
models. A column that the models give a server default but a migration forgets therefore looks
healthy in tests and fails only on a migrated database — exactly how ``provider_auth_events``
inserts broke in a staging run. This test migrates a throwaway database and checks the real
thing: no NOT NULL timestamp column may be missing a database-side default, and inserts that
rely on those defaults must work.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.skipif(
    os.environ.get("VELTRANE_SKIP_MIGRATION_TEST") == "1",
    reason="migration test disabled by VELTRANE_SKIP_MIGRATION_TEST",
)

ADMIN_DB = "postgres"


def _admin_engine():
    url = make_url(os.environ["VELTRANE_DATABASE_URL"]).set(database=ADMIN_DB)
    return create_engine(url, isolation_level="AUTOCOMMIT")


@pytest.fixture(scope="module")
def migrated_database():
    admin = _admin_engine()
    name = f"veltrane_mig_{uuid.uuid4().hex[:12]}"
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:  # pragma: no cover - depends on the role's privileges
        pytest.skip(f"cannot create a scratch database: {exc}")

    url = make_url(os.environ["VELTRANE_DATABASE_URL"]).set(database=name)
    try:
        # env.py reads the URL from application settings, so migrate in a child process
        # with the scratch database injected through the environment.
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            check=True,
            capture_output=True,
            env={**os.environ, "VELTRANE_DATABASE_URL": url.render_as_string(hide_password=False)},
        )
        yield url
    finally:
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


def test_server_defaults_from_the_models_exist_after_migration(migrated_database):
    """A server default the models rely on must be present in the migrated schema.

    The ORM omits such a column from an INSERT and lets PostgreSQL fill it, so a migration that
    forgets the default produces a NOT NULL violation at run time while every model-built test
    database stays green.
    """
    from app.db.models import Base

    engine = create_engine(migrated_database)
    inspector = inspect(engine)
    migrated_tables = set(inspector.get_table_names())
    problems: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in migrated_tables:
            problems.append(f"{table.name} (missing table)")
            continue
        present = {c["name"]: c for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.server_default is None:
                continue
            actual = present.get(column.name)
            if actual is None:
                problems.append(f"{table.name}.{column.name} (missing column)")
            elif actual["default"] is None:
                problems.append(f"{table.name}.{column.name}")
    engine.dispose()
    assert not problems, "Columns with a server default in the models have none after migrations: " + ", ".join(
        sorted(problems)
    )


def test_auth_event_insert_relies_on_the_database(migrated_database):
    """The staging failure: no created_at/updated_at supplied, insert must still succeed."""
    engine = create_engine(migrated_database)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO provider_auth_events (id, provider, event, outcome, detail, occurred_at) "
                "VALUES (gen_random_uuid(), 'deriv', 'session_connected', 'ok', '{}'::jsonb, now())"
            )
        )
        row = conn.execute(
            text("SELECT created_at, updated_at FROM provider_auth_events ORDER BY created_at DESC LIMIT 1")
        ).one()
    engine.dispose()
    assert row.created_at is not None
    assert row.updated_at is not None
