"""Deterministic stand-in for hosted crypto venues in the test suite.

The platform verifies a venue at connect time, which is correct behaviour but means a test
that connects to Binance would make a real signed request to api.binance.com. That is
unacceptable in CI: it needs network egress, it is geo-blocked in many regions and it
depends on the exchange being up.

``install_venue_stub`` swaps only the *network* surface of the CCXT adapters
(``test_connection`` and the balance/position readers). Everything else — credential
encryption, entitlements, audit records, error mapping — runs as in production.
Deriv is left alone: its integration tests point the adapter at a local server that speaks
the documented protocol.
"""

from __future__ import annotations

from contextlib import contextmanager

from app.providers.base import ProviderError
from app.services import connections as connections_service


class VenueStubState:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.fail_code: str | None = None
        self.fail_message = "venue unreachable"
        self.account_id = "STUB-ACCOUNT-1"
        self.balance_currencies = ["BTC", "USDT"]
        self.balances: list[dict] = [
            {"asset": "USDT", "free": 5000.0, "locked": 0.0, "total": 5000.0, "usd_value": 5000.0},
            {"asset": "BTC", "free": 0.1, "locked": 0.0, "total": 0.1, "usd_value": 4000.0},
        ]
        self.positions: list[dict] = []


STATE = VenueStubState()


class _StubVenue:
    """Wraps a real adapter, replacing only what would leave the process."""

    def __init__(self, real):
        self._real = real
        self.info = real.info
        self.capabilities = real.capabilities

    def __getattr__(self, name):
        return getattr(self._real, name)

    def _guard(self) -> None:
        if STATE.fail_code:
            raise ProviderError(STATE.fail_code, STATE.fail_message, retryable=True)

    def test_connection(self, credentials) -> dict:
        self._guard()
        return {
            "ok": True,
            "provider": self.info.key,
            "account_id": STATE.account_id,
            "balance_currencies": list(STATE.balance_currencies),
            "permissions": {"withdraw": False, "verified": True, "withdrawal_scope": "not_requested"},
        }

    def fetch_balances(self, credentials) -> list[dict]:
        self._guard()
        return [dict(row) for row in STATE.balances]

    def fetch_positions(self, credentials) -> list[dict]:
        self._guard()
        return [dict(row) for row in STATE.positions]


@contextmanager
def activate(monkeypatch):
    """Keep hosted crypto venues off the network for the duration of a test."""
    STATE.reset()
    real_get_provider = connections_service.get_provider

    def get_provider(key: str):
        adapter = real_get_provider(key)
        # The paper venue is local and the Deriv tests point their adapter at a mock gateway.
        if key in {"paper", "deriv"}:
            return adapter
        return _StubVenue(adapter)

    monkeypatch.setattr(connections_service, "get_provider", get_provider)
    try:
        yield STATE
    finally:
        STATE.reset()
