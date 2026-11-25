"""Simulated venue adapter.

Backs the ``paper`` provider so a user can add a sandbox account with no API keys.
Balances are deterministic and clearly labelled simulated; nothing here can reach a
real exchange.
"""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.providers.base import BaseAdapter, Capabilities, CredentialBundle, LiveTradingDisabled, ProviderInfo


class PaperProvider(BaseAdapter):
    info = ProviderInfo(
        key="paper",
        name="VELTRANE Simulation",
        kind="simulated",
        asset_classes=["crypto", "forex", "indices"],
        requires_passphrase=False,
        auth_style="none",
        docs_url="",
        status="implemented",
        notes="Local simulation venue. No real orders, no custody, no market connectivity.",
    )
    capabilities = Capabilities(
        read_balances=True,
        read_positions=True,
        read_orders=True,
        public_market_data=False,
        place_order=False,
        cancel_order=False,
        sandbox=True,
    )

    def test_connection(self, credentials: CredentialBundle) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "Simulation venue is always available. No credentials are used.",
            "permissions": {"read": True, "trade": False, "withdraw": False},
        }

    def fetch_balances(self, credentials: CredentialBundle) -> list[dict[str, Any]]:
        balance = float(settings.paper_starting_balance)
        return [
            {"asset": "USDT", "free": balance, "locked": 0.0, "total": balance, "usd_value": balance},
        ]

    def fetch_positions(self, credentials: CredentialBundle) -> list[dict[str, Any]]:
        return []

    def place_order(self, credentials: CredentialBundle, request: dict[str, Any]) -> dict[str, Any]:
        raise LiveTradingDisabled("The simulation venue does not accept live orders.")
