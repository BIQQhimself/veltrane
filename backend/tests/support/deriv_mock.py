"""A local server that speaks Deriv's documented protocol.

The production adapter talks to ``api.derivws.com``. Without a real token we cannot exercise
authorisation or execution against Deriv itself, so the test suite runs the same adapter code
against this server, which implements the shapes documented at developers.deriv.com:

* ``GET /v1/health``
* ``GET /trading/v1/options/accounts`` — Bearer token, plus ``Deriv-App-ID`` for PAT auth
* ``GET /account/v1/nickname``
* ``POST /trading/v1/options/accounts/{account_id}/otp`` -> ``{"data": {"url": ...}}``
* WS ``/trading/v1/options/ws/public`` — ping, active_symbols, ticks_history, proposal
* WS ``/trading/v1/options/ws/{demo|real}`` — portfolio, buy, sell, proposal_open_contract

It is deliberately strict about the header rules so a regression in the adapter's auth headers
fails the tests rather than silently passing.
"""

from __future__ import annotations

import math
import threading
import time
import uuid
from dataclasses import dataclass, field

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse


@dataclass
class MockState:
    token: str = "pat_test_token_0123456789abcdef"
    app_id: str = "12345"
    accounts: list[dict] = field(
        default_factory=lambda: [
            {
                "account_id": "VRTC900001",
                "account_type": "demo",
                "currency": "USD",
                "balance": 10000.0,
                "status": "active",
                "group": "row",
            },
            {
                "account_id": "CR700001",
                "account_type": "real",
                "currency": "USD",
                "balance": 250.0,
                "status": "active",
                "group": "row",
            },
        ]
    )
    nickname: str = "qa.trader"
    reject_token: bool = False
    require_app_id: bool = True
    otp_failures: int = 0  # fail the next N OTP calls, to exercise backoff
    otp_requests: int = 0
    contracts: dict[int, dict] = field(default_factory=dict)
    proposals: dict[str, dict] = field(default_factory=dict)
    socket_messages: list[dict] = field(default_factory=list)
    drop_after_buys: int | None = None
    # Roughly the spot each symbol trades at, so a quote for EUR/USD is not reported in
    # hundreds and a volatility index is not reported in single digits.
    price: float = 1234.5
    # Tests that need a specific pattern (an EMA cross, a stale series) supply one here. Ordering
    # is newest-first, exactly as the venue sends it, so the adapter's sort is exercised too.
    candle_override: list[dict] | None = None
    # OAuth: the token endpoint returns this token for a well-formed PKCE exchange.
    oauth_token: str = "ory_at_mock_access_token_0123456789"
    oauth_expires_in: int = 2592000
    oauth_reject: bool = False
    oauth_requests: list[dict] = field(default_factory=list)

    def reset(self) -> None:
        self.oauth_reject = False
        self.oauth_requests.clear()
        self.reject_token = False
        self.require_app_id = True
        self.otp_failures = 0
        self.otp_requests = 0
        self.contracts.clear()
        self.proposals.clear()
        self.socket_messages.clear()
        self.drop_after_buys = None
        self.candle_override = None
        for row in self.accounts:
            row["balance"] = 10000.0 if row["account_type"] == "demo" else 250.0


SYMBOL_PRICES: dict[str, float] = {
    "R_10": 6301.42,
    "R_25": 2704.18,
    "R_50": 302.86,
    "R_75": 90412.33,
    "R_100": 1234.5,
    "frxEURUSD": 1.0892,
    "frxGBPUSD": 1.2654,
    "frxUSDJPY": 152.97,
    "frxXAUUSD": 3242.65,
    "frxXAGUSD": 30.11,
    "cryBTCUSD": 63891.5,
    "cryETHUSD": 3242.65,
}


def _mock_price(state: MockState, epoch: int, symbol: str | None = None) -> float:
    base = SYMBOL_PRICES.get(symbol or "", state.price)
    phase = epoch / 90.0
    # Movement is a fraction of the spot, so a 0.7% wave looks the same on an index and on a pair.
    digits = 5 if base < 10 else (4 if base < 100 else 2)
    return round(base * (1 + 0.007 * math.sin(phase / 6.0) + 0.003 * math.cos(phase / 1.7)), digits)


def _mock_candle(state: MockState, epoch: int, granularity: int, symbol: str | None = None) -> dict:
    close = _mock_price(state, epoch, symbol)
    open_ = _mock_price(state, epoch - granularity, symbol)
    return {
        "epoch": epoch,
        "open": open_,
        "high": max(open_, close) + 1.0,
        "low": min(open_, close) - 1.0,
        "close": close,
    }


def _error(status: int, message: str, code: str = "Unauthorized") -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"errors": [{"status": status, "code": code, "message": message}], "meta": {}},
    )


def _authorise(request: Request, state: MockState) -> JSONResponse | None:
    header = request.headers.get("authorization", "")
    if not header:
        return _error(401, "Missing authorization header")
    if not header.lower().startswith("bearer "):
        return _error(401, "Invalid authorization header")
    token = header[7:].strip()
    oauth = token == state.oauth_token
    if state.reject_token or (not oauth and token != state.token):
        return _error(401, "Invalid token format")
    # OAuth tokens carry the client id at authorisation time; only PATs need the app header.
    if not oauth and state.require_app_id and request.headers.get("deriv-app-id") != state.app_id:
        return _error(401, "Deriv-App-ID header is required for PAT tokens")
    return None


def create_app(state: MockState) -> FastAPI:
    app = FastAPI()

    @app.get("/v1/health")
    def health() -> str:
        return "OK"

    @app.get("/trading/v1/options/accounts")
    def accounts(request: Request):
        failure = _authorise(request, state)
        if failure:
            return failure
        return {"data": [dict(row) for row in state.accounts], "meta": {"endpoint": "/accounts"}}

    @app.post("/oauth2/token")
    async def oauth_token(request: Request):
        """Authorization-code + PKCE exchange, shape per developers.deriv.com/docs/intro/oauth."""
        form = await request.form()
        payload = {key: str(value) for key, value in form.items()}
        state.oauth_requests.append(payload)
        if state.oauth_reject:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "code expired"}, status_code=400
            )
        verifier = payload.get("code_verifier", "")
        if payload.get("grant_type") != "authorization_code":
            return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
        if not payload.get("code", "").startswith("mock_code_"):
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        if not (43 <= len(verifier) <= 128):
            return JSONResponse({"error": "invalid_grant", "error_description": "bad verifier"}, status_code=400)
        if not payload.get("redirect_uri"):
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        return {
            "access_token": state.oauth_token,
            "token_type": "Bearer",
            "expires_in": state.oauth_expires_in,
            "scope": payload.get("scope") or "trade account_manage",
        }

    @app.get("/account/v1/nickname")
    def nickname(request: Request):
        failure = _authorise(request, state)
        if failure:
            return failure
        return {"data": {"nickname": state.nickname}, "meta": {}}

    @app.post("/trading/v1/options/accounts/{account_id}/otp")
    def otp(account_id: str, request: Request):
        failure = _authorise(request, state)
        if failure:
            return failure
        state.otp_requests += 1
        if state.otp_failures > 0:
            state.otp_failures -= 1
            return _error(500, "Upstream unavailable", code="InternalError")
        row = next((a for a in state.accounts if a["account_id"] == account_id), None)
        if row is None:
            return _error(404, "Account not found", code="NotFound")
        port = request.url.port or 80
        kind = "demo" if row["account_type"] == "demo" else "real"
        url = f"ws://127.0.0.1:{port}/trading/v1/options/ws/{kind}?otp={uuid.uuid4().hex}"
        return {"data": {"url": url}, "meta": {}}

    @app.websocket("/trading/v1/options/ws/public")
    async def public_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                message = await websocket.receive_json()
                await websocket.send_json(_public_reply(state, message))
        except (WebSocketDisconnect, RuntimeError):
            return

    @app.websocket("/trading/v1/options/ws/{kind}")
    async def trading_ws(websocket: WebSocket, kind: str) -> None:
        otp = websocket.query_params.get("otp", "")
        await websocket.accept()
        if not otp:
            await websocket.send_json(
                {"error": {"code": "InvalidOTP", "message": "One-time password missing"}, "msg_type": "error"}
            )
            await websocket.close()
            return
        try:
            while True:
                message = await websocket.receive_json()
                state.socket_messages.append(message)
                reply, close_after = _trading_reply(state, message, kind)
                if reply is not None:
                    await websocket.send_json(reply)
                if close_after:
                    await websocket.close()
                    return
        except (WebSocketDisconnect, RuntimeError):
            return

    return app


def _public_reply(state: MockState, message: dict) -> dict:
    req_id = message.get("req_id")
    base = {"req_id": req_id, "echo_req": message}
    if "ping" in message:
        return {**base, "msg_type": "ping", "ping": "pong"}
    if "active_symbols" in message:
        return {
            **base,
            "msg_type": "active_symbols",
            "active_symbols": [
                {
                    "underlying_symbol": "R_100",
                    "underlying_symbol_name": "Volatility 100 Index",
                    "market": "synthetic_index",
                    "pip_size": 0.01,
                    "exchange_is_open": 1,
                    "is_trading_suspended": 0,
                },
                {
                    "underlying_symbol": "frxEURUSD",
                    "underlying_symbol_name": "EUR/USD",
                    "market": "forex",
                    "pip_size": 0.0001,
                    "exchange_is_open": 1,
                    "is_trading_suspended": 0,
                },
            ],
        }
    if "contracts_for" in message:
        symbol = message["contracts_for"]
        return {
            **base,
            "msg_type": "contracts_for",
            "contracts_for": {
                "underlying_symbol": symbol,
                "available": [
                    {
                        "contract_type": contract_type,
                        "min_contract_duration": low,
                        "max_contract_duration": high,
                        "expiry_type": expiry,
                    }
                    for contract_type in ("CALL", "PUT", "DIGITODD")
                    for low, high, expiry in (
                        ("1t", "10t", "tick"),
                        ("15s", "1d", "intraday"),
                        ("1d", "365d", "daily"),
                    )
                ],
            },
        }
    if "ticks_history" in message:
        if message.get("style") == "candles" and state.candle_override:
            count = int(message.get("count") or len(state.candle_override))
            return {
                **base,
                "msg_type": "candles",
                "candles": list(state.candle_override[:count]),
                "pip_size": 2.0,
            }
        if message.get("style") == "candles":
            now = int(time.time())
            granularity = int(message.get("granularity") or 60)
            # A real venue never returns a flat series, and a flat one makes every indicator
            # blind (no EMA crossover can exist). This is a deterministic epoch-derived wave, so
            # the same instant always yields the same candles and tests stay reproducible.
            candles = [
                _mock_candle(state, now - granularity * (i + 1), granularity, message.get("ticks_history"))
                for i in range(int(message.get("count") or 1))
            ]
            return {**base, "msg_type": "candles", "candles": candles, "pip_size": 2.0}
        return {
            **base,
            "msg_type": "history",
            "history": {
                "prices": [_mock_price(state, int(time.time()), message.get("ticks_history"))],
                "times": [int(time.time())],
            },
            "pip_size": 2.0,
        }
    if "proposal" in message:
        if not message.get("underlying_symbol"):
            return {
                **base,
                "msg_type": "proposal",
                "error": {
                    "code": "InputValidationFailed",
                    "message": "Input validation failed: underlying_symbol",
                },
            }
        proposal_id = uuid.uuid4().hex + uuid.uuid4().hex
        amount = float(message.get("amount") or 10)
        state.proposals[proposal_id] = {
            "amount": amount,
            "contract_type": message.get("contract_type"),
            "underlying_symbol": message["underlying_symbol"],
            "currency": message.get("currency") or "USD",
        }
        return {
            **base,
            "msg_type": "proposal",
            "proposal": {
                "id": proposal_id,
                "ask_price": amount,
                "payout": round(amount * 1.95, 2),
                "spot": _mock_price(state, int(time.time()), message["underlying_symbol"]),
                "spot_time": int(time.time()),
                "date_start": int(time.time()),
                "date_expiry": int(time.time()) + 300,
                "longcode": f"Win payout if {message['underlying_symbol']} rises.",
            },
        }
    return {**base, "msg_type": "error", "error": {"code": "UnknownRequest", "message": "Unsupported"}}


def _trading_reply(state: MockState, message: dict, kind: str) -> tuple[dict | None, bool]:
    req_id = message.get("req_id")
    base = {"req_id": req_id, "echo_req": message}
    account = next((a for a in state.accounts if (a["account_type"] == "demo") == (kind == "demo")), None)

    if "portfolio" in message:
        open_rows = [row for row in state.contracts.values() if not row.get("is_sold")]
        return {**base, "msg_type": "portfolio", "portfolio": {"contracts": open_rows}}, False

    if "buy" in message:
        proposal = state.proposals.get(str(message["buy"]))
        if proposal is None:
            return (
                {
                    **base,
                    "msg_type": "buy",
                    "error": {"code": "ContractBuyValidationError", "message": "Unknown proposal"},
                },
                False,
            )
        contract_id = int(time.time() * 1000) % 10**9
        price = float(message.get("price") or proposal["amount"])
        if account:
            account["balance"] = round(float(account["balance"]) - price, 2)
        state.contracts[contract_id] = {
            "contract_id": contract_id,
            "buy_price": price,
            "payout": round(price * 1.95, 2),
            "profit": 0.0,
            "contract_type": proposal["contract_type"],
            "underlying_symbol": proposal["underlying_symbol"],
            "currency": proposal["currency"],
            "entry_spot": _mock_price(state, int(time.time()), proposal["underlying_symbol"]),
            "current_spot": _mock_price(state, int(time.time()), proposal["underlying_symbol"]),
            "is_sold": False,
            "purchase_time": int(time.time()),
            "expiry_time": int(time.time()) + 300,
        }
        buys = sum(1 for m in state.socket_messages if "buy" in m)
        close_after = state.drop_after_buys is not None and buys >= state.drop_after_buys
        return (
            {
                **base,
                "msg_type": "buy",
                "buy": {
                    "contract_id": contract_id,
                    "buy_price": price,
                    "payout": round(price * 1.95, 2),
                    "balance_after": account["balance"] if account else 0.0,
                    "transaction_id": contract_id + 1,
                    "longcode": f"Win payout if {proposal['underlying_symbol']} rises.",
                },
            },
            close_after,
        )

    if "sell" in message:
        contract = state.contracts.get(int(message["sell"]))
        if contract is None or contract["is_sold"]:
            return (
                {
                    **base,
                    "msg_type": "sell",
                    "error": {"code": "ContractNotFound", "message": "No such contract"},
                },
                False,
            )
        sold_for = round(float(contract["buy_price"]) * 0.92, 2)
        contract["is_sold"] = True
        contract["sell_price"] = sold_for
        contract["profit"] = round(sold_for - float(contract["buy_price"]), 2)
        if account:
            account["balance"] = round(float(account["balance"]) + sold_for, 2)
        return (
            {
                **base,
                "msg_type": "sell",
                "sell": {
                    "contract_id": contract["contract_id"],
                    "sold_for": sold_for,
                    "balance_after": account["balance"] if account else 0.0,
                    "transaction_id": contract["contract_id"] + 2,
                },
            },
            False,
        )

    if "proposal_open_contract" in message:
        contract = state.contracts.get(int(message.get("contract_id") or 0))
        if contract is None:
            return (
                {
                    **base,
                    "msg_type": "proposal_open_contract",
                    "error": {"code": "ContractNotFound", "message": "No such contract"},
                },
                False,
            )
        return {**base, "msg_type": "proposal_open_contract", "proposal_open_contract": dict(contract)}, False

    if "ping" in message:
        return {**base, "msg_type": "ping", "ping": "pong"}, False

    return (
        {**base, "msg_type": "error", "error": {"code": "UnknownRequest", "message": "Unsupported"}},
        False,
    )


class MockDerivServer:
    """Runs the mock in a background thread on an ephemeral port."""

    def __init__(self) -> None:
        self.state = MockState()
        self.app = create_app(self.state)
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self.port = 0

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def public_ws_url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/trading/v1/options/ws/public"

    def start(self) -> MockDerivServer:
        config = uvicorn.Config(self.app, host="127.0.0.1", port=0, log_level="warning", lifespan="off")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.time() + 15
        while time.time() < deadline:
            servers = getattr(self._server, "servers", None)
            if servers:
                for sock in servers[0].sockets:
                    self.port = sock.getsockname()[1]
                    break
            if self.port:
                break
            time.sleep(0.05)
        if not self.port:
            raise RuntimeError("Mock Deriv server did not start")
        import httpx

        for _ in range(200):
            try:
                if httpx.get(f"{self.base_url}/v1/health", timeout=1).status_code == 200:
                    return self
            except httpx.HTTPError:
                time.sleep(0.05)
        raise RuntimeError("Mock Deriv server did not become healthy")

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._server = None
        self._thread = None
