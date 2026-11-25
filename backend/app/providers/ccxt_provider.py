"""CCXT-backed crypto adapters (Binance, Bybit, OKX).

Public market data needs no credentials and is used by the paper engine.
Private calls are only made when the user supplies keys; withdrawal permission is
never requested and is actively checked where the venue exposes it.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import ccxt
from app.providers.base import (
    BaseAdapter,
    Candle,
    Capabilities,
    CredentialBundle,
    ProviderError,
    ProviderInfo,
    Ticker,
)

log = logging.getLogger(__name__)

TIMEFRAME_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}

# Withdrawal detection is only claimed where the venue exposes a permissions endpoint.
WITHDRAWAL_DETECTION = {"bybit", "okx"}


class CcxtProvider(BaseAdapter):
    def __init__(self, info: ProviderInfo, exchange_id: str):
        self.info = info
        self.exchange_id = exchange_id
        self.capabilities = Capabilities(
            read_balances=True,
            read_positions=True,
            read_orders=True,
            public_market_data=True,
            place_order=True,
            cancel_order=True,
            sandbox=exchange_id in {"binance", "bybit", "okx"},
            withdrawal_detection=exchange_id in WITHDRAWAL_DETECTION,
        )

    # ---------------- public market data ----------------
    def _public(self) -> ccxt.Exchange:
        klass = getattr(ccxt, self.exchange_id)
        return klass({"enableRateLimit": True, "timeout": 15_000})

    def fetch_ticker(self, symbol: str) -> Ticker:
        try:
            exchange = self._public()
            ticker = exchange.fetch_ticker(symbol)
        except ccxt.BaseError as exc:
            raise ProviderError("market_data_unavailable", f"{self.info.name} market data unavailable: {exc}") from exc
        price = ticker.get("last") or ticker.get("close")
        if not price:
            raise ProviderError("market_data_unavailable", f"{self.info.name} returned no price for {symbol}.")
        return Ticker(
            symbol=symbol,
            price=float(price),
            bid=float(ticker["bid"]) if ticker.get("bid") else None,
            ask=float(ticker["ask"]) if ticker.get("ask") else None,
            ts=int(ticker.get("timestamp") or time.time() * 1000),
            source=f"ccxt:{self.exchange_id}",
            extra={"high": ticker.get("high"), "low": ticker.get("low"), "volume": ticker.get("baseVolume")},
        )

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        if timeframe not in TIMEFRAME_MAP:
            raise ProviderError("unsupported_timeframe", f"Timeframe '{timeframe}' is not supported.")
        try:
            exchange = self._public()
            rows = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME_MAP[timeframe], limit=min(limit, 1000))
        except ccxt.BaseError as exc:
            raise ProviderError("market_data_unavailable", f"{self.info.name} candles unavailable: {exc}") from exc
        return [Candle(ts=int(r[0]), open=float(r[1]), high=float(r[2]), low=float(r[3]), close=float(r[4]), volume=float(r[5])) for r in rows]

    # ---------------- private (read-only) ----------------
    def _private(self, credentials: CredentialBundle) -> ccxt.Exchange:
        if not credentials.api_key or not credentials.api_secret:
            raise ProviderError("missing_credentials", "API key and secret are required.")
        klass = getattr(ccxt, self.exchange_id)
        config: dict[str, Any] = {
            "apiKey": credentials.api_key,
            "secret": credentials.api_secret,
            "enableRateLimit": True,
            "timeout": 20_000,
        }
        if self.info.requires_passphrase:
            config["password"] = credentials.passphrase
        return klass(config)

    def detect_permissions(self, credentials: CredentialBundle) -> dict:
        """Best-effort scope check. Never claims verification it cannot prove."""
        if self.exchange_id not in WITHDRAWAL_DETECTION:
            return {
                "withdrawal_scope": "unknown",
                "verified": False,
                "note": "This venue exposes no permissions endpoint through CCXT; withdrawal scope is unverified. "
                "Create the key without withdrawal rights and confirm manually.",
            }
        exchange = self._private(credentials)
        try:
            if not exchange.has.get("fetchPermissions"):
                raise AttributeError("no fetchPermissions")
            perms = exchange.fetch_permissions()
        except Exception as exc:  # noqa: BLE001
            return {
                "withdrawal_scope": "unknown",
                "verified": False,
                "note": f"Permissions endpoint unavailable: {type(exc).__name__}.",
            }
        return {"withdrawal_scope": "unknown", "verified": False, "raw": perms, "note": "Raw venue response recorded; withdrawal scope requires operator review."}

    def test_connection(self, credentials: CredentialBundle) -> dict:
        exchange = self._private(credentials)
        try:
            balance = exchange.fetch_balance()
            permissions = self.detect_permissions(credentials)
        except ccxt.AuthenticationError as exc:
            raise ProviderError("authentication_failed", f"{self.info.name} rejected the credentials.") from exc
        except ccxt.PermissionDenied as exc:
            raise ProviderError("permission_denied", f"{self.info.name} denied a read-only request: {exc}") from exc
        except ccxt.BaseError as exc:
            raise ProviderError("provider_error", f"{self.info.name} connection test failed: {exc}") from exc
        return {
            "ok": True,
            "provider": self.info.key,
            "balance_currencies": sorted([k for k, v in (balance.get("total") or {}).items() if v])[:25],
            "permissions": permissions,
        }

    def fetch_balances(self, credentials: CredentialBundle) -> list[dict]:
        exchange = self._private(credentials)
        try:
            balance = exchange.fetch_balance()
        except ccxt.BaseError as exc:
            raise ProviderError("provider_error", f"Balance fetch failed: {exc}") from exc
        rows = []
        for asset, total in (balance.get("total") or {}).items():
            if not total:
                continue
            rows.append(
                {
                    "asset": asset,
                    "total": float(total),
                    "free": float((balance.get("free") or {}).get(asset) or 0),
                    "locked": float((balance.get("used") or {}).get(asset) or 0),
                }
            )
        return rows

    def fetch_positions(self, credentials: CredentialBundle) -> list[dict]:
        exchange = self._private(credentials)
        if not exchange.has.get("fetchPositions"):
            return []
        try:
            positions = exchange.fetch_positions()
        except ccxt.BaseError as exc:
            raise ProviderError("provider_error", f"Position fetch failed: {exc}") from exc
        rows = []
        for pos in positions:
            contracts = float(pos.get("contracts") or 0)
            if not contracts:
                continue
            rows.append(
                {
                    "symbol": pos.get("symbol"),
                    "side": pos.get("side"),
                    "quantity": contracts,
                    "entry_price": float(pos.get("entryPrice") or 0),
                    "mark_price": float(pos.get("markPrice") or 0),
                    "unrealized_pnl": float(pos.get("unrealizedPnl") or 0),
                    "leverage": float(pos.get("leverage") or 1),
                }
            )
        return rows

    # ---------------- live execution ----------------
    def place_order(self, credentials: CredentialBundle, request: dict) -> dict:
        exchange = self._private(credentials)
        try:
            result = exchange.create_order(
                symbol=request["symbol"],
                type=request["order_type"],
                side=request["side"],
                amount=request["quantity"],
                price=request.get("price"),
                params={"stopLoss": request.get("stop_loss")} if request.get("stop_loss") else {},
            )
        except ccxt.InsufficientFunds as exc:
            raise ProviderError("insufficient_funds", f"Venue rejected the order: {exc}") from exc
        except ccxt.InvalidOrder as exc:
            raise ProviderError("invalid_order", f"Venue rejected the order: {exc}") from exc
        except ccxt.BaseError as exc:
            raise ProviderError("provider_error", f"Order submission failed: {exc}") from exc
        return {
            "provider_order_id": str(result.get("id")),
            "status": result.get("status") or "submitted",
            "filled": float(result.get("filled") or 0),
            "average": float(result.get("average") or result.get("price") or 0),
            "fee": float(((result.get("fee") or {}).get("cost")) or 0),
        }

    def cancel_order(self, credentials: CredentialBundle, provider_order_id: str, symbol: str) -> dict:
        exchange = self._private(credentials)
        try:
            result = exchange.cancel_order(provider_order_id, symbol)
        except ccxt.BaseError as exc:
            raise ProviderError("provider_error", f"Cancel failed: {exc}") from exc
        return {"status": result.get("status", "canceled"), "id": provider_order_id}


def build_providers() -> dict[str, CcxtProvider]:
    specs = [
        (
            ProviderInfo(
                key="binance",
                name="Binance",
                kind="exchange",
                asset_classes=["crypto"],
                docs_url="https://www.binance.com/en/support/faq/api",
                status="implemented_unverified",
                notes="Public market data + read-only account sync implemented. Live execution code path exists but is "
                "disabled platform-wide and has not been verified against a funded account.",
            ),
            "binance",
        ),
        (
            ProviderInfo(
                key="bybit",
                name="Bybit",
                kind="exchange",
                asset_classes=["crypto"],
                docs_url="https://bybit-exchange.github.io/docs/v5/intro",
                status="implemented_unverified",
                notes="Public market data + read-only account sync implemented. Live execution unverified.",
            ),
            "bybit",
        ),
        (
            ProviderInfo(
                key="okx",
                name="OKX",
                kind="exchange",
                asset_classes=["crypto"],
                requires_passphrase=True,
                docs_url="https://www.okx.com/docs-v5/en/",
                status="implemented_unverified",
                notes="Requires API passphrase. Public market data + read-only sync implemented. Live execution unverified.",
            ),
            "okx",
        ),
    ]
    return {info.key: CcxtProvider(info, ex) for info, ex in specs}
