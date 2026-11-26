"""Client for Deriv's current API (developers.deriv.com).

Three surfaces, per the official documentation:

* REST            ``https://api.derivws.com`` — ``Authorization: Bearer <token>`` and, when the
                  token is a Personal Access Token, ``Deriv-App-ID: <app id>``.
* Public WebSocket ``wss://api.derivws.com/trading/v1/options/ws/public`` — no auth. Ticks,
                  ``active_symbols``, ``proposal`` pricing, ``time``.
* Trading WebSocket — the URL comes from ``POST /trading/v1/options/accounts/{id}/otp``. The OTP is
                  embedded in the URL, so there is no auth message after connect.

Tokens are held in memory only and never logged. ``__repr__`` is redacted.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import threading
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

import httpx
from websockets.asyncio.client import connect as ws_connect

log = logging.getLogger(__name__)

DEFAULT_REST_BASE = "https://api.derivws.com"
PUBLIC_WS_URL = "wss://api.derivws.com/trading/v1/options/ws/public"
# Fallback only. Deriv issues per-app IDs; an unregistered ID is rejected for trading.
DEFAULT_APP_ID = "1089"


class DerivError(RuntimeError):
    """A Deriv failure with a stable code the API layer can map to a user-facing message."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int | None = None,
        retryable: bool = False,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable
        self.details = details or {}


class DerivAuthError(DerivError):
    pass


class DerivRateLimitError(DerivError):
    pass


@dataclass(frozen=True)
class DerivAccount:
    account_id: str
    account_type: str  # demo | real
    currency: str
    balance: float
    status: str = "active"
    group: str = ""

    @property
    def is_demo(self) -> bool:
        return self.account_type == "demo"

    def as_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "account_type": self.account_type,
            "currency": self.currency,
            "balance": self.balance,
            "status": self.status,
            "group": self.group,
            "is_demo": self.is_demo,
        }


@dataclass(frozen=True)
class DerivIdentity:
    accounts: list[DerivAccount]
    app_id: str
    token_kind: str = "pat"  # pat | oauth
    nickname: str = ""

    def account(self, account_id: str | None = None) -> DerivAccount | None:
        if not self.accounts:
            return None
        if account_id:
            for row in self.accounts:
                if row.account_id == account_id:
                    return row
            return None
        demo = [a for a in self.accounts if a.is_demo]
        return (demo or self.accounts)[0]


def _clean_token(token: str) -> str:
    value = (token or "").strip()
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    return value


def validate_token_shape(token: str) -> None:
    """Reject obviously malformed input before spending a network round trip.

    Deriv itself answers 401 "Invalid token format" for tokens that are not tokens; this only
    catches copy-paste accidents (empty, whitespace, a pasted header).
    """
    value = _clean_token(token)
    if not value:
        raise DerivAuthError("token_missing", "Enter your Deriv API token.")
    if any(ch.isspace() for ch in value) or len(value) < 8:
        raise DerivAuthError(
            "token_malformed",
            "That does not look like a Deriv API token. Copy the whole token with no spaces.",
        )


# --------------------------------------------------------------------------------------
# sync bridge
# --------------------------------------------------------------------------------------
def run_coro(coro: Coroutine[Any, Any, Any], *, timeout: float = 60.0) -> Any:
    """Run a coroutine from synchronous code (FastAPI threadpool workers, the scheduler).

    Uses ``asyncio.run`` when this thread has no loop; otherwise the coroutine runs on a
    dedicated thread with its own loop so a caller inside a loop cannot deadlock.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(asyncio.wait_for(coro, timeout=timeout))

    box: dict[str, Any] = {}

    def runner() -> None:
        try:
            box["value"] = asyncio.run(asyncio.wait_for(coro, timeout=timeout))
        except BaseException as exc:  # noqa: BLE001 - re-raised in the calling thread
            box["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout + 5)
    if "error" in box:
        raise box["error"]
    return box.get("value")


class AsyncWorker:
    """A dedicated event loop thread for long-lived WebSocket sessions.

    FastAPI endpoints are synchronous, but a trading socket must outlive a single request. Each
    session therefore owns one loop: coroutines are submitted to it and results are returned
    synchronously, so the same socket is never touched from two loops.
    """

    def __init__(self, name: str = "deriv-session") -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._started = threading.Event()
        self._closed = False
        self._thread.start()
        self._started.wait(timeout=5)

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._started.set()
        self._loop.run_forever()

    def submit(self, coro: Coroutine[Any, Any, Any], *, timeout: float = 60.0) -> Any:
        if self._closed:
            raise DerivError("worker_closed", "Session worker is closed.")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        if not self._loop.is_closed():
            self._loop.close()


# --------------------------------------------------------------------------------------
# REST
# --------------------------------------------------------------------------------------
class DerivREST:
    """Thin, explicit wrapper over the documented REST endpoints."""

    def __init__(
        self,
        token: str,
        *,
        app_id: str = DEFAULT_APP_ID,
        base_url: str = DEFAULT_REST_BASE,
        token_kind: str = "pat",
        timeout: float = 20.0,
    ) -> None:
        self._token = _clean_token(token)
        self.app_id = (app_id or DEFAULT_APP_ID).strip()
        self.base_url = base_url.rstrip("/")
        self.token_kind = token_kind
        self.timeout = timeout

    def __repr__(self) -> str:
        return f"DerivREST(app_id={self.app_id}, token=***, base={self.base_url})"

    def headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        if self.token_kind == "pat":
            headers["Deriv-App-ID"] = self.app_id
        return headers

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=self.timeout, headers=self.headers())

    def _handle(self, response: httpx.Response, *, operation: str) -> Any:
        if response.status_code < 400:
            try:
                payload = response.json()
            except ValueError:
                return {}
            return payload.get("data", payload)

        message = ""
        code = ""
        try:
            body = response.json()
            errors = body.get("errors") or []
            if errors:
                message = errors[0].get("message", "")
                code = errors[0].get("code", "")
        except ValueError:
            message = (response.text or "").strip()[:300]

        status = response.status_code
        lowered = f"{message}".lower()
        if status == 401:
            if "deriv-app-id" in lowered:
                raise DerivAuthError(
                    "app_id_required",
                    "Deriv requires the Deriv-App-ID header for API-token connections. "
                    "Set the App ID for this connection.",
                    status=status,
                    details={"operation": operation},
                )
            raise DerivAuthError(
                "invalid_token",
                "Deriv rejected the API token. Check it was copied whole, has the trade scope and "
                "has not been revoked.",
                status=status,
                details={"operation": operation, "deriv_message": message},
            )
        if status == 403:
            raise DerivAuthError(
                "missing_scope",
                "The token is valid but lacks the scope this operation needs. Recreate it with "
                "read, trade and account_manage as required.",
                status=status,
                details={"operation": operation, "deriv_message": message},
            )
        if status == 402:
            # Deriv answers 402 when the token's account cannot pay for the call: an unregistered
            # or unapproved app id, a zero-balance demo account, or an account blocked by the venue.
            raise DerivAuthError(
                "payment_required",
                "Deriv returned 402 Payment Required. Confirm the App ID matches the application the "
                "token was issued for, that the token has the read and trade scopes, and that the "
                "selected account has a balance. Nothing was sent to the venue.",
                status=status,
                details={"operation": operation, "deriv_message": message},
            )
        if status == 429:
            raise DerivRateLimitError(
                "rate_limited", "Deriv rate limit reached. Retrying shortly.", status=status, retryable=True
            )
        raise DerivError(
            code or "deriv_rest_error",
            message or f"Deriv returned HTTP {status} for {operation}.",
            status=status,
            retryable=status >= 500,
            details={"operation": operation},
        )

    def _get(self, path: str, *, operation: str, attempts: int = 3) -> Any:
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                with self._client() as client:
                    return self._handle(client.get(path), operation=operation)
            except (httpx.TransportError, DerivRateLimitError) as exc:
                last = exc
                if attempt + 1 < attempts:
                    time.sleep(min(2**attempt * 0.5 + random.random() * 0.2, 4.0))
                    continue
                raise DerivError(
                    "deriv_unreachable",
                    "Could not reach Deriv. Check the platform's outbound network access.",
                    retryable=True,
                    details={"operation": operation, "cause": type(exc).__name__},
                ) from exc
        raise DerivError("deriv_unreachable", "Could not reach Deriv.", retryable=True) from last

    def health(self) -> bool:
        try:
            with self._client() as client:
                return client.get("/v1/health").status_code == 200
        except httpx.HTTPError:
            return False

    def accounts(self) -> list[DerivAccount]:
        data = self._get("/trading/v1/options/accounts", operation="accounts")
        rows = data if isinstance(data, list) else (data or {}).get("data", [])
        out: list[DerivAccount] = []
        for row in rows or []:
            try:
                out.append(
                    DerivAccount(
                        account_id=str(row["account_id"]),
                        account_type=str(row.get("account_type") or "real").lower(),
                        currency=str(row.get("currency") or "USD"),
                        balance=float(row.get("balance") or 0),
                        status=str(row.get("status") or "active"),
                        group=str(row.get("group") or ""),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def identity(self, *, token_kind: str | None = None, nickname: bool = True) -> DerivIdentity:
        kind = token_kind or self.token_kind
        accounts = self.accounts()
        name = ""
        if nickname:
            try:
                data = self._get("/account/v1/nickname", operation="nickname", attempts=1)
                if isinstance(data, dict):
                    name = str(data.get("nickname") or data.get("email") or "")
            except DerivError:
                # account_manage is optional for trading; a missing scope is not fatal.
                name = ""
        return DerivIdentity(accounts=accounts, app_id=self.app_id, token_kind=kind, nickname=name)

    def otp_url(self, account_id: str) -> str:
        try:
            with self._client() as client:
                response = client.post(f"/trading/v1/options/accounts/{account_id}/otp")
        except httpx.TransportError as exc:
            raise DerivError(
                "deriv_unreachable",
                "Could not reach Deriv to open a trading session.",
                retryable=True,
                details={"cause": type(exc).__name__},
            ) from exc
        data = self._handle(response, operation="otp")
        url = ""
        if isinstance(data, dict):
            url = str(data.get("url") or (data.get("data") or {}).get("url") or "")
        if not url.startswith(("wss://", "ws://")):
            raise DerivError("otp_invalid", "Deriv did not return a usable trading session URL.")
        return url


# --------------------------------------------------------------------------------------
# WebSocket
# --------------------------------------------------------------------------------------
class DerivSocket:
    """One WebSocket connection with request/response correlation.

    Reconnection is deliberately *not* handled here: a trading socket needs a fresh OTP, so
    ``DerivTradingSession`` owns the reconnect policy.
    """

    def __init__(self, url: str, *, open_timeout: float = 20.0) -> None:
        self.url = url
        self.open_timeout = open_timeout
        self._ws: Any = None
        self._req_id = 0
        self._lock = asyncio.Lock()
        self._pending: dict[int, asyncio.Future] = {}
        self._listeners: list[Callable[[dict], None]] = []
        self._reader: asyncio.Task | None = None
        self.closed = False
        self.last_message_at: float | None = None

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self.closed

    async def __aenter__(self) -> DerivSocket:
        await self.open()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()

    async def open(self) -> None:
        self._ws = await ws_connect(self.url, open_timeout=self.open_timeout, max_size=8 * 1024 * 1024)
        self.closed = False
        self._reader = asyncio.create_task(self._read_loop())

    async def close(self) -> None:
        self.closed = True
        if self._reader:
            self._reader.cancel()
            try:
                await self._reader
            except (asyncio.CancelledError, Exception):
                pass
            self._reader = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001 - closing a broken socket must not raise
                pass
            self._ws = None
        for future in self._pending.values():
            if not future.done():
                future.set_exception(DerivError("socket_closed", "Trading session closed.", retryable=True))
        self._pending.clear()

    def add_listener(self, listener: Callable[[dict], None]) -> None:
        self._listeners.append(listener)

    async def _read_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                self.last_message_at = time.time()
                try:
                    message = json.loads(raw)
                except ValueError:
                    continue
                req_id = message.get("req_id")
                if req_id is not None and req_id in self._pending:
                    future = self._pending.pop(req_id)
                    if not future.done():
                        future.set_result(message)
                for listener in self._listeners:
                    try:
                        listener(message)
                    except Exception:  # noqa: BLE001 - a listener must not kill the reader
                        log.warning("deriv_listener_failed")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface as a closed session
            log.info("deriv_socket_closed", extra={"extra_fields": {"reason": type(exc).__name__}})
        finally:
            self.closed = True
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(DerivError("socket_closed", "Trading session dropped.", retryable=True))
            self._pending.clear()

    async def send(self, payload: dict) -> None:
        if self._ws is None or self.closed:
            raise DerivError("socket_closed", "Trading session is not connected.", retryable=True)
        await self._ws.send(json.dumps(payload))

    async def request(self, payload: dict, *, timeout: float = 25.0) -> dict:
        if self._ws is None or self.closed:
            raise DerivError("socket_closed", "Trading session is not connected.", retryable=True)
        async with self._lock:
            self._req_id += 1
            req_id = self._req_id
        body = {**payload, "req_id": req_id}
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = future
        try:
            await self.send(body)
            message = await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError as exc:
            self._pending.pop(req_id, None)
            raise DerivError(
                "timeout",
                f"Deriv did not answer '{next(iter(payload))}' in time.",
                retryable=True,
            ) from exc
        finally:
            self._pending.pop(req_id, None)

        error = message.get("error")
        if error:
            code = str(error.get("code") or "deriv_error")
            text = str(error.get("message") or "Deriv rejected the request.")
            if code in {"InvalidToken", "Unauthorized", "AuthorizationRequired"}:
                raise DerivAuthError(code, text, details=error)
            if code == "RateLimit":
                raise DerivRateLimitError(code, text, retryable=True)
            raise DerivError(code, text, details=error)
        return message


@dataclass
class SessionState:
    connected: bool = False
    account_id: str = ""
    account_type: str = ""
    currency: str = ""
    balance: float | None = None
    otp_issued_at: float | None = None
    connected_at: float | None = None
    last_error: str | None = None
    last_error_at: float | None = None
    reconnects: int = 0
    consecutive_failures: int = 0
    suspended: bool = False
    suspension_reason: str | None = None
    last_reconcile_at: float | None = None
    open_contracts: int = 0

    def as_dict(self) -> dict:
        return {
            "connected": self.connected,
            "account_id": self.account_id,
            "account_type": self.account_type,
            "currency": self.currency,
            "balance": self.balance,
            "connected_at": self.connected_at,
            "otp_issued_at": self.otp_issued_at,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at,
            "reconnects": self.reconnects,
            "consecutive_failures": self.consecutive_failures,
            "suspended": self.suspended,
            "suspension_reason": self.suspension_reason,
            "last_reconcile_at": self.last_reconcile_at,
            "open_contracts": self.open_contracts,
        }


class DerivTradingSession:
    """An OTP-authenticated trading socket with a controlled reconnect policy.

    The class is synchronous on purpose: the platform's provider interface is synchronous and the
    socket must survive between requests. Every call is dispatched onto the session's own event
    loop (``AsyncWorker``), so the socket is only ever touched by one loop.

    ``trading_paused`` is set the moment the socket drops and is only cleared by
    ``resume_checks``, which re-reads the account and reconciles open contracts.
    """

    def __init__(
        self,
        rest: DerivREST,
        account_id: str,
        *,
        account_type: str = "",
        currency: str = "",
        max_consecutive_failures: int = 5,
        worker: AsyncWorker | None = None,
    ) -> None:
        self.rest = rest
        self.account_id = account_id
        self.state = SessionState(account_id=account_id, account_type=account_type, currency=currency)
        self.max_consecutive_failures = max_consecutive_failures
        self.socket: DerivSocket | None = None
        self.trading_paused = True
        self.pause_reason = "not_connected"
        self._worker = worker or AsyncWorker()
        self._owns_worker = worker is None

    # ------------------------------------------------------------------ public API
    def connect(self) -> dict:
        return self._worker.submit(self._connect())

    def reconnect(self, *, attempts: int = 4) -> dict:
        return self._worker.submit(self._reconnect(attempts=attempts), timeout=120)

    def resume_checks(self, *, allowed: bool) -> dict:
        return self._worker.submit(self._resume_checks(allowed=allowed))

    def request(self, payload: dict, *, timeout: float = 25.0) -> dict:
        return self._worker.submit(self._request(payload, timeout=timeout), timeout=timeout + 10)

    def close(self) -> None:
        if self.socket is not None or self.state.connected:
            try:
                self._worker.submit(self._close(), timeout=20)
            except Exception:  # noqa: BLE001 - closing must never raise into the caller
                pass
        self.state.connected = False
        self.trading_paused = True
        self.pause_reason = "closed"
        if self._owns_worker:
            self._worker.close()

    def suspend(self, reason: str) -> None:
        self.state.suspended = True
        self.state.suspension_reason = reason
        self.trading_paused = True
        self.pause_reason = f"suspended: {reason}"

    @property
    def connected(self) -> bool:
        return bool(self.socket and self.socket.connected)

    def as_dict(self) -> dict:
        return {
            **self.state.as_dict(),
            "trading_paused": self.trading_paused,
            "pause_reason": self.pause_reason,
        }

    # ------------------------------------------------------------------ async internals
    async def _connect(self) -> dict:
        url = await asyncio.to_thread(self.rest.otp_url, self.account_id)
        self.state.otp_issued_at = time.time()
        socket = DerivSocket(url)
        await socket.open()
        self.socket = socket
        self.state.connected = True
        self.state.connected_at = time.time()
        self.state.last_error = None
        self.trading_paused = True  # stays paused until resume checks pass
        self.pause_reason = "awaiting_safety_checks"
        return {"connected": True, "account_id": self.account_id}

    async def _reconnect(self, *, attempts: int = 4) -> dict:
        await self._close()
        self.state.connected = False
        delay = 1.0
        for attempt in range(1, attempts + 1):
            try:
                await self._connect()
                self.state.reconnects += 1
                self.state.consecutive_failures = 0
                return {"connected": True, "attempts": attempt}
            except DerivAuthError as exc:
                self.state.last_error = exc.message
                self.state.last_error_at = time.time()
                self.state.consecutive_failures += 1
                self.suspend(f"authentication_failed: {exc.message}")
                raise
            except DerivError as exc:
                self.state.last_error = exc.message
                self.state.last_error_at = time.time()
                self.state.consecutive_failures += 1
                log.info(
                    "deriv_reconnect_failed",
                    extra={"extra_fields": {"attempt": attempt, "code": exc.code}},
                )
                if attempt == attempts:
                    break
                await asyncio.sleep(delay + random.random() * 0.3)
                delay = min(delay * 2, 30.0)
        if self.state.consecutive_failures >= self.max_consecutive_failures:
            self.suspend("persistent_connection_failures")
        raise DerivError(
            "reconnect_failed",
            self.state.last_error or "Could not re-establish the Deriv trading session.",
            retryable=True,
        )

    async def _resume_checks(self, *, allowed: bool) -> dict:
        checks: list[dict] = []

        def record(name: str, ok: bool, detail: str = "") -> bool:
            checks.append({"check": name, "ok": ok, "detail": detail})
            return ok

        if not record("authorization_active", allowed, "Live trading authorisation is required."):
            self.trading_paused = True
            self.pause_reason = "authorization_missing"
            return {"resumed": False, "checks": checks}

        if not record("socket_connected", bool(self.socket and self.socket.connected)):
            self.trading_paused = True
            self.pause_reason = "socket_closed"
            return {"resumed": False, "checks": checks}

        try:
            accounts = await asyncio.to_thread(self.rest.accounts)
            match = next((a for a in accounts if a.account_id == self.account_id), None)
            ok = match is not None
            if match is not None:
                self.state.balance = match.balance
                self.state.currency = match.currency
                self.state.account_type = match.account_type
            record(
                "account_identity",
                ok,
                self.account_id if ok else "Account not present in the token's account list",
            )
        except DerivError as exc:
            record("account_identity", False, exc.message)

        try:
            portfolio = await self._request({"portfolio": 1})
            contracts = (portfolio.get("portfolio") or {}).get("contracts") or []
            self.state.open_contracts = len(contracts)
            self.state.last_reconcile_at = time.time()
            record("open_contracts_reconciled", True, f"{len(contracts)} open")
        except DerivError as exc:
            record("open_contracts_reconciled", False, exc.message)

        record(
            "not_suspended",
            not self.state.suspended,
            self.state.suspension_reason or "",
        )

        resumed = all(item["ok"] for item in checks)
        self.trading_paused = not resumed
        self.pause_reason = "" if resumed else "safety_checks_failed"
        return {"resumed": resumed, "checks": checks}

    async def _request(self, payload: dict, *, timeout: float = 25.0) -> dict:
        if self.socket is None or not self.socket.connected:
            raise DerivError("socket_closed", "Trading session is not connected.", retryable=True)
        return await self.socket.request(payload, timeout=timeout)

    async def _close(self) -> None:
        if self.socket is not None:
            await self.socket.close()
        self.socket = None
        self.state.connected = False

    def __repr__(self) -> str:
        return f"DerivTradingSession(account={self.account_id}, connected={self.connected})"


async def public_request(payload: dict, *, timeout: float = 20.0, url: str = PUBLIC_WS_URL) -> dict:
    """One-shot request against the unauthenticated public gateway."""
    async with DerivSocket(url, open_timeout=timeout) as socket:
        return await socket.request(payload, timeout=timeout)


def fetch_public(payload: dict, *, timeout: float = 20.0, url: str = PUBLIC_WS_URL) -> dict:
    return run_coro(public_request(payload, timeout=timeout, url=url), timeout=timeout + 10)


__all__ = [
    "AsyncWorker",
    "DEFAULT_APP_ID",
    "DEFAULT_REST_BASE",
    "PUBLIC_WS_URL",
    "DerivAccount",
    "DerivAuthError",
    "DerivError",
    "DerivIdentity",
    "DerivREST",
    "DerivRateLimitError",
    "DerivSocket",
    "DerivTradingSession",
    "SessionState",
    "fetch_public",
    "public_request",
    "run_coro",
    "validate_token_shape",
]
