"""Deriv adapter — forex and indices.

Status: scaffold. Deriv's API is WebSocket-based and requires an application id and
an OAuth/API token. Until a verified implementation exists, every private operation
raises a clear error rather than pretending to work.
"""
from __future__ import annotations

from app.providers.base import BaseAdapter, Capabilities, CredentialBundle, ProviderError, ProviderInfo


class DerivProvider(BaseAdapter):
    def __init__(self) -> None:
        self.info = ProviderInfo(
            key="deriv",
            name="Deriv",
            kind="broker",
            asset_classes=["forex", "index"],
            auth_style="oauth_or_token",
            docs_url="https://api.deriv.com/",
            status="scaffold",
            notes="Forex and index routing requires Deriv's WebSocket API with an application id. "
            "Not implemented in this build; no connectivity is claimed.",
        )
        self.capabilities = Capabilities(
            public_market_data=False,
            read_balances=False,
            read_positions=False,
            place_order=False,
            cancel_order=False,
            withdrawal_detection=False,
        )

    def _not_implemented(self, operation: str):
        raise ProviderError(
            "provider_not_implemented",
            f"Deriv '{operation}' is not implemented. The adapter is a documented scaffold and is not "
            "verified for connectivity. Use paper trading or a supported crypto venue.",
        )

    def test_connection(self, credentials: CredentialBundle) -> dict:
        self._not_implemented("test_connection")

    def fetch_balances(self, credentials: CredentialBundle) -> list[dict]:
        self._not_implemented("fetch_balances")

    def fetch_positions(self, credentials: CredentialBundle) -> list[dict]:
        self._not_implemented("fetch_positions")

    def fetch_ticker(self, symbol: str):
        self._not_implemented("fetch_ticker")

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int):
        self._not_implemented("fetch_ohlcv")
