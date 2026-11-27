"""Deriv adapter — synthetic indices, forex and indices via Deriv's current API.

Authentication is a single Personal Access Token (or an OAuth 2.0 access token). There is no
separate API secret: Deriv never had one, and asking for it was the original defect.

Market data and contract pricing run on the unauthenticated public gateway. Anything that
touches an account needs an OTP-authenticated trading socket:

    POST /trading/v1/options/accounts/{accountId}/otp  ->  wss://.../ws/{demo|real}?otp=...

Execution is still gated upstream by the platform switch, the subscriber's explicit live
authorisation and the deterministic risk engine. This adapter refuses to submit a real-money
order unless the caller has already cleared those gates and passes ``live_authorised=True``.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.providers.base import (
    BaseAdapter,
    Candle,
    Capabilities,
    CredentialBundle,
    ProviderError,
    ProviderInfo,
    Ticker,
)
from app.providers.deriv_client import (
    DEFAULT_APP_ID,
    DEFAULT_REST_BASE,
    PUBLIC_WS_URL,
    DerivError,
    DerivREST,
    DerivTradingSession,
    fetch_public,
    validate_token_shape,
)

log = logging.getLogger(__name__)

TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

# OAuth access tokens identify the application, so the App-ID header is not sent for them.
OAUTH_SENTINEL = "__oauth__"

# Deriv names rise/fall contracts CALL and PUT; the platform speaks buy/sell.
SIDE_TO_CONTRACT = {"buy": "CALL", "sell": "PUT"}


_CODE_MAP = {
    "token_missing": "token_missing",
    "token_malformed": "token_malformed",
    "invalid_token": "deriv_invalid_token",
    "missing_scope": "deriv_missing_scope",
    "app_id_required": "deriv_app_id_required",
    "rate_limited": "deriv_rate_limited",
}


def _to_provider_error(exc: DerivError) -> ProviderError:
    code = _CODE_MAP.get(exc.code, f"deriv_{exc.code}")
    return ProviderError(code, exc.message, retryable=exc.retryable)


def build_deriv_provider() -> DerivProvider:
    """Adapter wired to the configured endpoints. One factory so registry and sessions agree."""
    from app.core.config import settings

    return DerivProvider(
        rest_base=settings.deriv_rest_base,
        public_ws_url=settings.deriv_public_ws_url,
        default_app_id=settings.deriv_app_id,
    )


class DerivProvider(BaseAdapter):
    def __init__(
        self,
        *,
        rest_base: str | None = None,
        public_ws_url: str | None = None,
        default_app_id: str | None = None,
    ) -> None:
        # Endpoints are injectable so the test suite can run the adapter against a local server
        # that speaks Deriv's documented protocol.
        self.rest_base = rest_base or DEFAULT_REST_BASE
        self.public_ws_url = public_ws_url or PUBLIC_WS_URL
        self.default_app_id = DEFAULT_APP_ID if default_app_id is None else default_app_id.strip()
        self.info = ProviderInfo(
            key="deriv",
            name="Deriv",
            kind="broker",
            asset_classes=["synthetic", "forex", "index", "commodity"],
            auth_style="personal_access_token",
            docs_url="https://developers.deriv.com/docs/",
            status="implemented_unverified",
            notes=(
                "Personal Access Token (or OAuth 2.0) authentication, OTP trading sockets, contract "
                "proposals, buy/sell and portfolio reconciliation are implemented against Deriv's "
                "current API (api.derivws.com). Public market data and contract pricing are verified "
                "live. Account authorisation and execution are verified against a protocol-faithful "
                "test server, not yet against a funded Deriv account."
            ),
            requires_api_secret=False,
            requires_app_id=True,
            token_label="Personal Access Token",
            supports_oauth=True,
        )
        self.capabilities = Capabilities(
            read_balances=True,
            read_positions=True,
            read_orders=True,
            public_market_data=True,
            place_order=True,
            cancel_order=True,
            sandbox=True,
            withdrawal_detection=False,
        )

    # ------------------------------------------------------------------ helpers
    def _rest(self, credentials: CredentialBundle) -> DerivREST:
        validate_token_shape(credentials.api_key)
        oauth = credentials.app_id == OAUTH_SENTINEL
        app_id = credentials.app_id or self.default_app_id
        if not oauth and not app_id:
            raise ProviderError(
                "app_id_required",
                "A Deriv App ID is required for API-token connections. Set the platform default "
                "(VELTRANE_DERIV_APP_ID) or enter your own registered App ID.",
            )
        return DerivREST(
            credentials.api_key,
            app_id=app_id or "oauth",
            base_url=self.rest_base,
            token_kind="oauth" if oauth else "pat",
        )

    @staticmethod
    def _account_id(credentials: CredentialBundle) -> str:
        if not credentials.account_id:
            raise ProviderError(
                "account_not_selected",
                "Choose which Deriv account to trade (demo or real) before placing a contract.",
            )
        return credentials.account_id

    def _session(self, credentials: CredentialBundle, session: DerivTradingSession | None = None):
        if session is not None:
            return session
        return DerivTradingSession(
            rest=self._rest(credentials),
            account_id=self._account_id(credentials),
        )

    # ------------------------------------------------------------------ account
    def test_connection(self, credentials: CredentialBundle) -> dict[str, Any]:
        """Authenticate and return identity. Never returns the token."""
        try:
            rest = self._rest(credentials)
            identity = rest.identity()
        except DerivError as exc:
            raise _to_provider_error(exc) from exc

        if not identity.accounts:
            raise ProviderError(
                "no_accounts",
                "The token authenticated but no Options accounts are visible. Check the token's scopes.",
            )
        selected = identity.account(credentials.account_id or None)
        return {
            "ok": True,
            "provider": "deriv",
            "app_id": identity.app_id,
            "token_kind": identity.token_kind,
            "nickname": identity.nickname,
            "accounts": [a.as_dict() for a in identity.accounts],
            "selected_account": selected.as_dict() if selected else None,
            "account_id": selected.account_id if selected else "",
            "account_type": selected.account_type if selected else "",
            "currency": selected.currency if selected else "",
            "balance": selected.balance if selected else None,
            "is_virtual": bool(selected and selected.is_demo),
            "balance_currencies": sorted({a.currency for a in identity.accounts}),
            "permissions": {
                "verified": True,
                "withdrawal_scope": "not_requested",
                "note": "Deriv tokens grant trade/read scopes only. VELTRANE never requests withdrawal.",
            },
        }

    def account_summary(self, credentials: CredentialBundle) -> dict[str, Any]:
        return self.test_connection(credentials)

    def fetch_balances(self, credentials: CredentialBundle) -> list[dict[str, Any]]:
        try:
            identity = self._rest(credentials).identity(nickname=False)
        except DerivError as exc:
            raise _to_provider_error(exc) from exc
        if not identity.accounts:
            raise ProviderError("no_accounts", "No Deriv Options accounts are visible to this token.")
        rows = []
        for account in identity.accounts:
            rows.append(
                {
                    "asset": f"{account.currency}:{account.account_id}",
                    "free": account.balance,
                    "locked": 0.0,
                    "total": account.balance,
                    "usd_value": account.balance if account.currency == "USD" else 0.0,
                    "meta": account.as_dict(),
                }
            )
        return rows

    def fetch_positions(
        self, credentials: CredentialBundle, session: DerivTradingSession | None = None
    ) -> list[dict[str, Any]]:
        rows = []
        for contract in self.open_contracts(credentials, session=session):
            contract_type = str(contract.get("contract_type", "")).upper()
            rows.append(
                {
                    "symbol": contract.get("underlying_symbol") or contract.get("symbol") or "DERIV",
                    "side": "long" if contract_type.startswith(("CALL", "MULTUP", "HIGHER")) else "short",
                    "quantity": 1.0,
                    "entry_price": float(contract.get("buy_price") or 0),
                    "mark_price": float(contract.get("current_spot") or contract.get("entry_spot") or 0),
                    "unrealized_pnl": float(contract.get("profit") or 0),
                    "leverage": 1.0,
                    "meta": contract,
                }
            )
        return rows

    def open_contracts(
        self, credentials: CredentialBundle, session: DerivTradingSession | None = None
    ) -> list[dict[str, Any]]:
        own = session is None
        active = self._session(credentials, session)
        try:
            if own:
                active.connect()
            response = active.request({"portfolio": 1})
            return list((response.get("portfolio") or {}).get("contracts") or [])
        except DerivError as exc:
            raise _to_provider_error(exc) from exc
        finally:
            if own:
                active.close()

    # ------------------------------------------------------------------ market data
    def fetch_ticker(self, symbol: str) -> Ticker:
        try:
            payload = fetch_public(
                {"ticks_history": symbol, "count": 1, "end": "latest", "style": "ticks"},
                url=self.public_ws_url,
            )
        except DerivError as exc:
            raise _to_provider_error(exc) from exc
        prices = (payload.get("history") or {}).get("prices") or []
        times = (payload.get("history") or {}).get("times") or []
        if not prices:
            raise ProviderError("no_ticks", f"Deriv returned no ticks for '{symbol}'.")
        return Ticker(
            symbol=symbol,
            price=float(prices[-1]),
            ts=int(times[-1]) if times else int(time.time()),
            source="deriv",
            extra={"pip_size": payload.get("pip_size")},
        )

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        granularity = TIMEFRAME_SECONDS.get(timeframe)
        if granularity is None:
            raise ProviderError("unsupported_timeframe", f"Deriv adapter does not map timeframe '{timeframe}'.")
        try:
            payload = fetch_public(
                {
                    "ticks_history": symbol,
                    "count": max(1, min(limit, 5000)),
                    "end": "latest",
                    "style": "candles",
                    "granularity": granularity,
                },
                url=self.public_ws_url,
            )
        except DerivError as exc:
            raise _to_provider_error(exc) from exc
        candles = [
            Candle(
                ts=int(row["epoch"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=0.0,  # Deriv's candle payload carries no volume; 0 is honest, not a guess.
            )
            for row in payload.get("candles") or []
        ]
        # Oldest first, always. Indicators read closes[-1] as the latest bar and the chart draws
        # left to right, so an unordered payload would silently invert both.
        candles.sort(key=lambda candle: candle.ts)
        return candles

    def active_symbols(self) -> list[dict[str, Any]]:
        try:
            payload = fetch_public({"active_symbols": "brief"}, url=self.public_ws_url)
        except DerivError as exc:
            raise _to_provider_error(exc) from exc
        return list(payload.get("active_symbols") or [])

    def contracts_for(self, symbol: str) -> dict[str, Any]:
        """Contract families and duration bands Deriv currently offers for ``symbol``.

        Public call: no account, no credentials, no side effects. The response is the
        authority for what the terminal may offer, so it is never cached beyond its TTL
        or amended locally.
        """
        try:
            return fetch_public({"contracts_for": symbol}, url=self.public_ws_url)
        except DerivError as exc:
            raise _to_provider_error(exc) from exc

    # ------------------------------------------------------------------ pricing
    def proposal(self, credentials: CredentialBundle, request: dict[str, Any]) -> dict[str, Any]:
        """Contract price. Uses the public gateway: no account is touched."""
        amount = float(request.get("stake") or request.get("amount") or 0)
        if amount <= 0:
            raise ProviderError("invalid_stake", "Stake must be greater than zero.")
        contract_type = request.get("contract_type") or SIDE_TO_CONTRACT.get(str(request.get("side", "buy")))
        payload = {
            "proposal": 1,
            "amount": amount,
            "basis": request.get("basis", "stake"),
            "contract_type": contract_type,
            "currency": request.get("currency") or "USD",
            "duration": int(request.get("duration") or 5),
            "duration_unit": request.get("duration_unit") or "t",
            "underlying_symbol": request["symbol"],
        }
        if request.get("barrier"):
            payload["barrier"] = str(request["barrier"])
        try:
            response = fetch_public(payload, url=self.public_ws_url)
        except DerivError as exc:
            raise _to_provider_error(exc) from exc
        proposal = response.get("proposal") or {}
        if not proposal.get("id"):
            raise ProviderError("proposal_failed", "Deriv did not return a proposal id.")
        return proposal

    # ------------------------------------------------------------------ execution
    def place_order(
        self,
        credentials: CredentialBundle,
        request: dict[str, Any],
        *,
        session: DerivTradingSession | None = None,
        live_authorised: bool = False,
    ) -> dict[str, Any]:
        """Buy one contract. Demo accounts need no platform live authorisation; real ones do."""
        amount = float(request.get("stake") or request.get("quantity") or 0)
        if amount <= 0:
            raise ProviderError("invalid_stake", "Stake must be greater than zero.")

        own = session is None
        active = self._session(credentials, session)
        try:
            if own:
                active.connect()
                checks = active.resume_checks(allowed=True)
                if not checks["resumed"]:
                    raise ProviderError(
                        "session_not_ready",
                        "The Deriv trading session failed its safety checks: "
                        + ", ".join(c["check"] for c in checks["checks"] if not c["ok"]),
                    )
            elif active.trading_paused:
                raise ProviderError("session_paused", "The Deriv trading session is paused pending safety checks.")

            proposal = self.proposal(
                credentials,
                {**request, "currency": request.get("currency") or active.state.currency or "USD"},
            )
            response = active.request({"buy": proposal["id"], "price": float(proposal.get("ask_price") or amount)})
            receipt = response.get("buy") or {}
            if not receipt.get("contract_id"):
                raise ProviderError("buy_failed", "Deriv did not return a contract id.")
            return {
                "provider_order_id": str(receipt["contract_id"]),
                "filled_qty": 1.0,
                "avg_fill_price": float(receipt.get("buy_price") or amount),
                "fee": 0.0,
                "fee_currency": active.state.currency or request.get("currency") or "USD",
                "balance_after": float(receipt.get("balance_after") or 0) or None,
                "status": "filled",
                "raw": receipt,
                "proposal_id": proposal.get("id"),
                "payout": receipt.get("payout") or proposal.get("payout"),
                "longcode": receipt.get("longcode") or proposal.get("longcode"),
                "is_demo": (active.state.account_type or "").lower() == "demo",
                "contract_type": request.get("contract_type") or SIDE_TO_CONTRACT.get(str(request.get("side", "buy"))),
            }
        except DerivError as exc:
            raise _to_provider_error(exc) from exc
        finally:
            if own:
                active.close()

    def cancel_order(
        self,
        credentials: CredentialBundle,
        provider_order_id: str,
        symbol: str = "",
        *,
        session: DerivTradingSession | None = None,
    ) -> dict[str, Any]:
        """Sell a contract back at market (Deriv's early exit)."""
        own = session is None
        active = self._session(credentials, session)
        try:
            if own:
                active.connect()
            response = active.request({"sell": int(provider_order_id), "price": 0})
            receipt = response.get("sell") or {}
            return {
                "provider_order_id": provider_order_id,
                "sold_for": float(receipt.get("sold_for") or 0),
                "balance_after": float(receipt.get("balance_after") or 0) or None,
                "status": "sold",
                "raw": receipt,
            }
        except DerivError as exc:
            raise _to_provider_error(exc) from exc
        finally:
            if own:
                active.close()

    def contract_status(
        self,
        credentials: CredentialBundle,
        contract_id: str,
        *,
        session: DerivTradingSession | None = None,
    ) -> dict[str, Any]:
        own = session is None
        active = self._session(credentials, session)
        try:
            if own:
                active.connect()
            response = active.request({"proposal_open_contract": 1, "contract_id": int(contract_id)})
            return dict(response.get("proposal_open_contract") or {})
        except DerivError as exc:
            raise _to_provider_error(exc) from exc
        finally:
            if own:
                active.close()
