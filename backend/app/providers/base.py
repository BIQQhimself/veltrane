from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class ProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class LiveTradingDisabled(ProviderError):
    def __init__(self, message: str = "Live order submission is disabled by platform policy."):
        super().__init__("live_trading_disabled", message)


@dataclass(frozen=True)
class ProviderInfo:
    key: str
    name: str
    kind: str  # exchange | broker
    asset_classes: list[str]
    requires_passphrase: bool = False
    auth_style: str = "api_key"
    docs_url: str = ""
    status: str = "scaffold"  # scaffold | implemented_unverified | read_only_verified | live_verified
    notes: str = ""


@dataclass(frozen=True)
class Capabilities:
    read_balances: bool = False
    read_positions: bool = False
    read_orders: bool = False
    public_market_data: bool = False
    place_order: bool = False
    cancel_order: bool = False
    sandbox: bool = False
    withdrawal_detection: bool = False

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class CredentialBundle:
    api_key: str = ""
    api_secret: str = ""
    passphrase: str = ""
    account_id: str = ""
    app_id: str = ""

    def __repr__(self) -> str:  # never leak secrets through logs or tracebacks
        return f"CredentialBundle(api_key=***{self.api_key[-4:] if self.api_key else ''}, passphrase={'set' if self.passphrase else 'unset'})"


@dataclass
class Ticker:
    symbol: str
    price: float
    bid: float | None = None
    ask: float | None = None
    ts: int | None = None
    source: str = "unknown"
    extra: dict = field(default_factory=dict)


@dataclass
class Candle:
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class BaseProvider(Protocol):
    info: ProviderInfo
    capabilities: Capabilities

    def fetch_ticker(self, symbol: str) -> Ticker: ...

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[Candle]: ...

    def test_connection(self, credentials: CredentialBundle) -> dict[str, Any]: ...

    def fetch_balances(self, credentials: CredentialBundle) -> list[dict[str, Any]]: ...

    def fetch_positions(self, credentials: CredentialBundle) -> list[dict[str, Any]]: ...

    def place_order(self, credentials: CredentialBundle, request: dict[str, Any]) -> dict[str, Any]: ...

    def cancel_order(self, credentials: CredentialBundle, provider_order_id: str, symbol: str) -> dict[str, Any]: ...


class BaseAdapter:
    """Shared behaviour for adapters that are not yet verified for an operation."""

    info: ProviderInfo
    capabilities: Capabilities

    def _unsupported(self, operation: str):
        raise ProviderError(
            "not_supported",
            f"{self.info.name} adapter does not implement '{operation}' yet.",
        )

    def fetch_ticker(self, symbol: str) -> Ticker:
        self._unsupported("fetch_ticker")

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        self._unsupported("fetch_ohlcv")

    def test_connection(self, credentials: CredentialBundle) -> dict[str, Any]:
        self._unsupported("test_connection")

    def fetch_balances(self, credentials: CredentialBundle) -> list[dict[str, Any]]:
        self._unsupported("fetch_balances")

    def fetch_positions(self, credentials: CredentialBundle) -> list[dict[str, Any]]:
        self._unsupported("fetch_positions")

    def place_order(self, credentials: CredentialBundle, request: dict[str, Any]) -> dict[str, Any]:
        raise LiveTradingDisabled()

    def cancel_order(self, credentials: CredentialBundle, provider_order_id: str, symbol: str) -> dict[str, Any]:
        raise LiveTradingDisabled()
