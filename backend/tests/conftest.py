"""Test harness.

Tests run against a real PostgreSQL database (``veltrane_test``) with the demo market
data feed, so the code paths exercised are the production code paths. Redis is used
for rate limiting and is flushed between tests.
"""
from __future__ import annotations

import base64
import os
import uuid

from dotenv import load_dotenv

# The app's settings load .env itself, but this module must resolve the test
# database URL before app.core.config is imported, so read the same files first.
load_dotenv(".env")
load_dotenv("../.env")

_TEST_DB_URL = os.environ.get("VELTRANE_TEST_DATABASE_URL", "").strip()
if not _TEST_DB_URL:
    _base_url = os.environ.get("VELTRANE_DATABASE_URL", "").strip()
    if _base_url:
        _TEST_DB_URL = _base_url.rsplit("/", 1)[0] + "/veltrane_test"
if not _TEST_DB_URL:
    raise RuntimeError(
        "Set VELTRANE_TEST_DATABASE_URL (or VELTRANE_DATABASE_URL) before running the "
        "test suite. See ENVIRONMENT_VARIABLES.md."
    )

os.environ["VELTRANE_ENV"] = "test"
os.environ["VELTRANE_DATABASE_URL"] = _TEST_DB_URL
os.environ["VELTRANE_SECRET_KEY"] = "test-secret-key-0123456789abcdef0123456789abcdef"
os.environ["VELTRANE_MASTER_ENCRYPTION_KEY"] = base64.b64encode(bytes(range(32))).decode()
os.environ["VELTRANE_MARKET_DATA_SOURCE"] = "demo"
os.environ["VELTRANE_BILLING_PROVIDER"] = "mock"
os.environ["VELTRANE_REQUIRE_EMAIL_VERIFICATION"] = "true"
os.environ["VELTRANE_REDIS_URL"] = "redis://127.0.0.1:6379/9"
os.environ["VELTRANE_LIVE_TRADING_ENABLED"] = "false"
os.environ["VELTRANE_DEMO_MARKET_DATA_ENABLED"] = "true"
os.environ["VELTRANE_LOG_LEVEL"] = "WARNING"

import pytest  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.redis_client import get_redis  # noqa: E402
from app.db.models import Base, FeatureFlag, RiskPolicy, SystemSetting, User  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.risk.types import DEFAULT_RISK_RULES  # noqa: E402
from app.services import analytics, entitlements, performance_fees, strategy_service  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# Password assigned to accounts these fixtures create. Test-only, never used outside the suite.
PASSWORD = "Veltrane!Test2026"
BASE = "/api/v1"


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _reset_state():
    from sqlalchemy import text

    with engine.begin() as conn:
        tables = ", ".join(f'"{t}"' for t in Base.metadata.tables)
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    client = get_redis()
    if client is not None:
        client.flushdb()
    import app.core.rate_limit as rate_limit

    rate_limit._memory.clear()

    db = SessionLocal()
    try:
        entitlements.seed_plans(db)
        strategy_service.seed_system_strategies(db)
        db.add(RiskPolicy(org_id=None, name="global", version=1, rules=dict(DEFAULT_RISK_RULES), is_active=True))
        db.add(SystemSetting(key=analytics.COST_SETTING_KEY, value=dict(analytics.DEFAULT_COSTS)))
        db.add(SystemSetting(key=performance_fees.SETTING_KEY, value=dict(performance_fees.DEFAULT_SETTINGS)))
        for key in ("live_trading_ui", "portfolio_optimization", "ai_strategy_generation", "performance_fees"):
            db.add(FeatureFlag(key=key, enabled=False, description="test"))
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def unique_email(prefix: str = "trader") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


def register(client, email: str | None = None, password: str = PASSWORD, full_name: str = "Test Trader") -> dict:
    email = email or unique_email()
    response = client.post(
        f"{BASE}/auth/register",
        json={"email": email, "password": password, "full_name": full_name, "country": "GB", "accept_terms": True},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    token = body["debug_verification_token"]
    verified = client.post(f"{BASE}/auth/verify-email", json={"token": token})
    assert verified.status_code == 200, verified.text
    return {"email": email, "password": password, "user": body["user"]}


def login(client, email: str, password: str = PASSWORD) -> dict:
    response = client.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    body = response.json()
    return {
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
        "access_token": body["access_token"],
        "csrf_token": body["csrf_token"],
        "user": body["user"],
    }


@pytest.fixture
def make_user(client):
    def _make(prefix: str = "trader", verified: bool = True) -> dict:
        email = unique_email(prefix)
        if verified:
            data = register(client, email=email)
            session = login(client, email)
        else:
            response = client.post(
                f"{BASE}/auth/register",
                json={
                    "email": email,
                    "password": PASSWORD,
                    "full_name": "Unverified",
                    "country": "GB",
                    "accept_terms": True,
                },
            )
            assert response.status_code == 201
            data = {"email": email, "password": PASSWORD, "user": response.json()["user"]}
            session = {"headers": {}, "user": data["user"]}
        return {
            **data,
            **session,
            "user_id": data["user"]["id"],
            "org_id": data["user"]["org_id"],
        }

    return _make


@pytest.fixture
def trader(make_user):
    return make_user("trader")


@pytest.fixture
def trader2(make_user):
    return make_user("trader2")


@pytest.fixture
def pro_trader(client, make_user):
    account = make_user("pro")
    checkout = client.post(
        f"{BASE}/billing/checkout",
        json={"plan_code": "pro"},
        headers=account["headers"],
    )
    assert checkout.status_code == 200, checkout.text
    token = checkout.json()["checkout_token"]
    done = client.post(
        f"{BASE}/billing/mock/complete",
        json={"checkout_token": token},
        headers=account["headers"],
    )
    assert done.status_code == 200, done.text
    refreshed = login(client, account["email"])
    return {**account, **refreshed}


@pytest.fixture
def elite_trader(client, make_user):
    account = make_user("elite")
    checkout = client.post(f"{BASE}/billing/checkout", json={"plan_code": "elite"}, headers=account["headers"])
    assert checkout.status_code == 200
    client.post(
        f"{BASE}/billing/mock/complete",
        json={"checkout_token": checkout.json()["checkout_token"]},
        headers=account["headers"],
    )
    refreshed = login(client, account["email"])
    return {**account, **refreshed}


@pytest.fixture
def staff(client, make_user, db):
    account = make_user("staff")
    user = db.get(User, account["user_id"])
    user.is_staff = True
    user.staff_role = "owner"
    db.commit()
    refreshed = login(client, account["email"])
    return {**account, **refreshed}


@pytest.fixture
def admin(client, make_user, db):
    account = make_user("admin")
    user = db.get(User, account["user_id"])
    user.is_staff = True
    user.staff_role = "admin"
    db.commit()
    return account


def mark_connection_connected(db, connection_id: str) -> None:
    """Simulate a verified read-only sync so live-authorisation preconditions can be tested."""
    from datetime import datetime, timezone

    from app.db.models import Connection

    connection = db.get(Connection, connection_id)
    connection.status = "connected"
    connection.last_sync_at = datetime.now(timezone.utc)
    db.commit()


def place_order(client, headers, **overrides) -> dict:
    payload = {
        "symbol": "BTC/USDT",
        "side": "buy",
        "quantity": 0.01,
        "order_type": "market",
        "mode": "paper",
        "reason": "Test order",
    }
    payload.update(overrides)
    response = client.post(f"{BASE}/orders", json=payload, headers=headers)
    return {"status_code": response.status_code, "body": response.json() if response.content else {}}
