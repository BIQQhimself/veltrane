"""Deriv endpoints: market data, contract previews, sessions and live contracts.

Every execution path here goes through ``app.trading.deriv_execution``, which runs the execution
gate and the independent risk engine before the adapter is allowed to submit anything.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from urllib.parse import quote

from app.api.deps import get_current_user
from app.core import rate_limit as limit
from app.core.config import settings
from app.core.errors import bad_request, forbidden, not_found
from app.db.constants import AuditAction, TradingRule
from app.db.models import Connection, User
from app.db.session import get_db
from app.services import (
    audit,
    automation_limits,
    contract_catalogue,
    deriv_oauth,
    deriv_sessions,
    execution_gate,
    referrals,
)
from app.services.connections import get_connection, load_credentials
from app.trading import deriv_execution
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

router = APIRouter(prefix="/deriv", tags=["deriv"])

_SYMBOL_CACHE: dict[str, object] = {"at": None, "rows": []}
SYMBOL_TTL_SECONDS = 300


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ContractRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    side: str = Field(default="buy", pattern="^(buy|sell)$")
    contract_type: str = Field(default="", max_length=24)
    stake: float = Field(gt=0, le=1_000_000)
    duration: int = Field(default=TradingRule.MIN_DURATION_SECONDS, ge=1, le=86_400)
    duration_unit: str = Field(default="s", pattern="^(t|s|m|h|d)$")
    currency: str = Field(default="", max_length=8)
    reason: str = Field(default="", max_length=500)
    idempotency_key: str = Field(default="", max_length=120)
    source: str = Field(default="human", max_length=32)

    @model_validator(mode="after")
    def _duration_floor(self):
        """Refuse a sub-minute term before the request reaches the execution layer."""
        if TradingRule.below_floor(self.duration, self.duration_unit):
            raise ValueError(
                f"The shortest contract on VELTRANE is {TradingRule.MIN_DURATION_SECONDS} seconds."
            )
        return self



def _deriv_connection(db: Session, org_id: str, connection_id: str) -> Connection:
    connection = get_connection(db, org_id, connection_id)
    if connection.provider != "deriv":
        raise bad_request("not_deriv", "This connection is not a Deriv connection.")
    return connection


# ------------------------------------------------------------------ market data
@router.get("/symbols")
def symbols(refresh: bool = Query(default=False)):
    """Deriv's tradable universe, straight from the public gateway."""
    cached_at = _SYMBOL_CACHE["at"]
    fresh = isinstance(cached_at, datetime) and (_utcnow() - cached_at).total_seconds() < SYMBOL_TTL_SECONDS
    if not refresh and fresh:
        rows = _SYMBOL_CACHE["rows"]
        source = "cache"
    else:
        adapter = deriv_sessions.adapter()
        rows = adapter.active_symbols()
        _SYMBOL_CACHE["rows"] = rows
        _SYMBOL_CACHE["at"] = _utcnow()
        source = "live"
    markets: dict[str, list[dict]] = {}
    for row in rows:
        markets.setdefault(row.get("market") or "other", []).append(
            {
                "symbol": row.get("underlying_symbol"),
                "name": row.get("underlying_symbol_name"),
                "market": row.get("market"),
                "submarket": row.get("submarket"),
                "pip_size": row.get("pip_size"),
                "exchange_is_open": bool(row.get("exchange_is_open")),
                "suspended": bool(row.get("is_trading_suspended")),
            }
        )
    return {
        "source": "sandbox" if settings.deriv_sandbox else source,
        "sandbox": settings.deriv_sandbox,
        "count": len(rows),
        "markets": markets,
    }


@router.get("/contracts")
def contracts(
    symbol: str = Query(min_length=1, max_length=32),
    currency: str = Query(default="USD", min_length=3, max_length=8),
    refresh: bool = Query(default=False),
    user: User = Depends(get_current_user),
):
    """Contract families and durations Deriv actually offers for ``symbol`` right now.

    This is the single source of truth for the duration selector and for the agent: both
    read the same discovered menu. When Deriv cannot be reached the response says so and
    carries no menu, so no surface can fall back to a hardcoded list.
    """
    adapter = deriv_sessions.adapter()
    catalogue = contract_catalogue.get(symbol, currency, provider=adapter, refresh=refresh)
    return contract_catalogue.tradeable_catalogue(catalogue)


@router.get("/candles")
def candles(
    symbol: str = Query(min_length=1, max_length=32),
    timeframe: str = Query(default="1m"),
    limit: int = Query(default=200, ge=1, le=1000),
    user: User = Depends(get_current_user),
):
    adapter = deriv_sessions.adapter()
    rows = adapter.fetch_ohlcv(symbol, timeframe, limit)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "source": "sandbox" if settings.deriv_sandbox else "deriv",
        "sandbox": settings.deriv_sandbox,
        "candles": [{"t": c.ts, "o": c.open, "h": c.high, "l": c.low, "c": c.close, "v": c.volume} for c in rows],
    }


@router.get("/ticker")
def ticker(symbol: str = Query(min_length=1, max_length=32), user: User = Depends(get_current_user)):
    adapter = deriv_sessions.adapter()
    quote = adapter.fetch_ticker(symbol)
    return {
        "symbol": quote.symbol,
        "price": quote.price,
        "ts": quote.ts,
        "source": "sandbox" if settings.deriv_sandbox else quote.source,
        "sandbox": settings.deriv_sandbox,
        "age_seconds": max(0.0, _utcnow().timestamp() - quote.ts),
    }


# ------------------------------------------------------------------ connection state
@router.get("/connections/{connection_id}/status")
def connection_status(connection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    connection = _deriv_connection(db, user.org_id, connection_id)
    gate = execution_gate.evaluate(db, user=user, connection=connection)
    session = deriv_sessions.get_session(connection.id)
    contracts: list[dict] = []
    contracts_error = ""
    if session is not None and session.connected:
        try:
            contracts = deriv_sessions.adapter().open_contracts(load_credentials(db, connection), session=session)
        except Exception as exc:  # noqa: BLE001 - surface the reason, never fake an empty list
            contracts_error = str(exc)
    return {
        "connection": {
            "id": connection.id,
            "label": connection.label,
            "status": connection.status,
            "environment": connection.environment,
            "account_id": connection.provider_account_id,
            "account_type": connection.provider_account_type,
            "currency": connection.provider_currency,
            "is_demo": (connection.provider_account_type or "").lower() == "demo",
            "last_sync_at": connection.last_sync_at.isoformat() if connection.last_sync_at else None,
            "last_auth_error": connection.last_auth_error,
            "accounts": (connection.provider_meta or {}).get("accounts", []),
            "nickname": (connection.provider_meta or {}).get("nickname", ""),
        },
        "session": session.as_dict() if session is not None else (connection.session_state or {}),
        "gate": gate.as_dict(),
        "open_contracts": contracts,
        "contracts_error": contracts_error,
        "app_id": settings.deriv_app_id,
    }


@router.post("/connections/{connection_id}/session/connect")
def session_connect(connection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    connection = _deriv_connection(db, user.org_id, connection_id)
    gate = execution_gate.evaluate(db, user=user, connection=connection)
    if not gate.allowed:
        raise forbidden("execution_blocked", gate.blocking_message, {"gate": gate.as_dict()})
    session = deriv_sessions.session_for(db, connection, allowed=True)
    db.commit()
    return {"session": session.as_dict()}


@router.post("/connections/{connection_id}/session/reconnect")
def session_reconnect(connection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    connection = _deriv_connection(db, user.org_id, connection_id)
    gate = execution_gate.evaluate(db, user=user, connection=connection)
    result = deriv_sessions.reconnect(db, connection, allowed=gate.allowed)
    db.commit()
    return {"session": result, "gate": gate.as_dict()}


@router.post("/connections/{connection_id}/session/close")
def session_close(connection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    connection = _deriv_connection(db, user.org_id, connection_id)
    deriv_sessions.close_session(connection.id)
    connection.session_state = {"connected": False, "closed_by": user.email}
    db.commit()
    return {"status": "closed"}


# ------------------------------------------------------------------ contracts
@router.post("/connections/{connection_id}/preview")
def preview(
    connection_id: str,
    payload: ContractRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    connection = _deriv_connection(db, user.org_id, connection_id)
    return deriv_execution.preview(db, user=user, connection=connection, payload=payload.model_dump())


@router.post("/connections/{connection_id}/contracts", status_code=201)
def open_contract(
    connection_id: str,
    payload: ContractRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    connection = _deriv_connection(db, user.org_id, connection_id)
    result = deriv_execution.open_contract(
        db,
        user=user,
        connection=connection,
        payload=payload.model_dump(),
        source=payload.source,
        reason=payload.reason,
        idempotency_key=payload.idempotency_key or None,
    )
    db.commit()
    return result


@router.get("/connections/{connection_id}/contracts")
def list_contracts(connection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    connection = _deriv_connection(db, user.org_id, connection_id)
    result = deriv_execution.sync_positions(db, connection=connection)
    db.commit()
    return result


@router.post("/connections/{connection_id}/contracts/{contract_id}/close")
def close_contract(
    connection_id: str,
    contract_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    connection = _deriv_connection(db, user.org_id, connection_id)
    result = deriv_execution.close_contract(db, user=user, connection=connection, contract_id=contract_id)
    db.commit()
    return result


@router.get("/trades/{order_id}")
def trade_detail(order_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return deriv_execution.trade_detail(db, org_id=user.org_id, order_id=order_id)


# ------------------------------------------------------------------ OAuth 2.0 (Deriv)
class OAuthStartRequest(BaseModel):
    purpose: str = Field(default="connect", pattern="^(connect|reconnect)$")
    connection_id: str = Field(default="", max_length=64)
    visitor_id: str = Field(default="", max_length=64)


class OAuthExchangeRequest(BaseModel):
    code: str = Field(min_length=8, max_length=2048)
    state: str = Field(min_length=8, max_length=128)


class AccountSwitchRequest(BaseModel):
    account_id: str = Field(min_length=3, max_length=64)


@router.get("/oauth/status")
def oauth_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """What the Connect panel needs. Never returns tokens or client secrets."""
    link = referrals.link_config(db)
    connection = (
        db.query(Connection)
        .filter(Connection.org_id == user.org_id, Connection.provider == "deriv")
        .order_by(Connection.created_at)
        .first()
    )
    return {
        "configured": deriv_oauth.configured(),
        "client_id": settings.deriv_oauth_client_id,
        "redirect_uri": settings.deriv_oauth_redirect,
        "scopes": deriv_oauth.requested_scopes(),
        "single_account_policy": True,
        "referral": {"url": link["url"] if link["enabled"] else "", "enabled": link["enabled"]},
        "connection": (
            {
                "id": connection.id,
                "status": connection.status,
                "account_id": connection.provider_account_id,
                "account_type": connection.provider_account_type,
                "currency": connection.provider_currency,
                "accounts": (connection.provider_meta or {}).get("accounts", []),
                "nickname": (connection.provider_meta or {}).get("nickname", ""),
                "token": deriv_oauth.token_state(connection),
            }
            if connection
            else None
        ),
        "note": (
            "Deriv issues no refresh token: when the access token expires, reconnect from this panel."
            if connection
            else "Connect with your Deriv login. VELTRANE never asks for withdrawal permission."
        ),
    }


@router.post("/oauth/start")
def oauth_start(
    payload: OAuthStartRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Begin the authorisation-code + PKCE handshake.

    Returns the Deriv URL to open in the current tab and the referral link to open in a new
    tab for people who do not have a Deriv account yet.
    """
    limit.enforce(request, "deriv_oauth_start", limit=12, window=600)
    link = referrals.link_config(db)
    result = deriv_oauth.authorize_url(
        db,
        user=user,
        purpose=payload.purpose,
        connection_id=payload.connection_id,
        visitor_id=referrals.valid_visitor(payload.visitor_id),
    )
    referrals.record_oauth_start(
        db, user=user, visitor_id=payload.visitor_id, purpose=payload.purpose
    )
    audit.record(
        db,
        action="deriv.oauth_started",
        org_id=user.org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        target_type="deriv_oauth_state",
        target_id=result["state"],
        meta={"purpose": payload.purpose, "scopes": result["scopes"]},
    )
    db.commit()
    return {**result, "referral_url": referrals.signup_url(link)}


@router.post("/oauth/exchange")
def oauth_exchange(
    payload: OAuthExchangeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Complete the handshake from a browser that received the callback."""
    result = deriv_oauth.complete(db, state=payload.state, code=payload.code, user=user)
    referrals.record_connection(
        db,
        user=user,
        connection_id=result["connection_id"],
        accounts=len(result["identity"]["accounts"]),
    )
    db.commit()
    return {"status": "connected", **result}


@router.get("/oauth/callback")
def oauth_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
    error_description: str = Query(default=""),
    db: Session = Depends(get_db),
):
    """Deriv's redirect target.

    The browser arrives here without a VELTRANE session, so the single-use ``state`` row is
    what authorises the exchange. The result is a redirect to the app either way: this route
    is never an API for scripts.
    """
    web = settings.web_base_url.rstrip("/")
    if error:
        log.info("deriv_oauth_denied", extra={"extra_fields": {"error": error}})
        return RedirectResponse(
            f"{web}/app/accounts?deriv=denied&reason={quote(error_description or error)[:120]}", status_code=302
        )
    if not code or not state:
        return RedirectResponse(f"{web}/app/accounts?deriv=invalid", status_code=302)
    try:
        result = deriv_oauth.complete(db, state=state, code=code)
        owner = db.get(User, db.query(Connection).filter(Connection.id == result["connection_id"]).first().created_by)
        if owner is not None:
            referrals.record_connection(
                db,
                user=owner,
                connection_id=result["connection_id"],
                accounts=len(result["identity"]["accounts"]),
            )
        db.commit()
    except Exception as exc:  # noqa: BLE001 - the browser must always land somewhere useful
        db.rollback()
        code_name = getattr(exc, "code", "deriv_oauth_failed")
        log.exception("deriv_oauth_callback_failed", extra={"extra_fields": {"code": str(code_name)}})
        return RedirectResponse(f"{web}/app/accounts?deriv=error&reason={quote(str(code_name))[:80]}", status_code=302)
    return RedirectResponse(
        f"{web}/app/accounts?deriv=connected&accounts={len(result['identity']['accounts'])}", status_code=302
    )


@router.post("/connections/{connection_id}/account")
def switch_deriv_account(
    connection_id: str,
    payload: AccountSwitchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Switch between the demo and real accounts under one Deriv authorisation."""
    connection = _deriv_connection(db, user.org_id, connection_id)
    result = deriv_oauth.switch_account(db, connection=connection, account_id=payload.account_id)
    audit.record(
        db,
        action="deriv.account_switched",
        org_id=user.org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        target_type="connection",
        target_id=connection.id,
        meta={"account_type": result["account_type"]},
    )
    db.commit()
    return {"status": "switched", "connection_id": connection.id, **result}


@router.post("/referral/click")
def referral_click(
    payload: OAuthStartRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record that a signed-in user opened the referral link to create a Deriv account."""
    limit.enforce(request, "deriv_referral_click", limit=10, window=3600)
    event = referrals.record_click(
        db, visitor_id=payload.visitor_id, referrer="app.accounts", landing="deriv-signup"
    )
    db.commit()
    return {"status": "recorded", "event_id": event.id}


# ------------------------------------------------------------------ automation
class AutomationRequest(BaseModel):
    enabled: bool = False
    mode: str = Field(default="approval", pattern="^(approval|autonomous)$")
    symbol: str = Field(default="R_100", min_length=1, max_length=32)
    contract_type: str = Field(default="CALL", max_length=24)
    stake: float = Field(default=10.0, gt=0, le=100_000)
    duration: int = Field(default=TradingRule.MIN_DURATION_SECONDS, ge=1, le=86_400)
    duration_unit: str = Field(default="s", pattern="^(t|s|m|h|d)$")
    max_open_contracts: int = Field(default=1, ge=0, le=50)
    max_stake_per_trade: float = Field(default=25.0, gt=0, le=100_000)
    daily_loss_limit: float = Field(default=100.0, gt=0, le=1_000_000)
    daily_stake_limit: float = Field(default=250.0, gt=0, le=1_000_000)
    cooldown_seconds: int = Field(default=300, ge=0, le=86_400)
    signal_ttl_seconds: int = Field(default=600, ge=30, le=86_400)
    # Empty/None keeps the single-symbol behaviour; a list turns on market-wide scanning.
    universe: list[str] | None = Field(default=None, max_length=40)
    sector_cap: int = Field(default=2, ge=1, le=5)

    @model_validator(mode="after")
    def _duration_floor(self):
        """Refuse a sub-minute term before the request reaches the execution layer."""
        if TradingRule.below_floor(self.duration, self.duration_unit):
            raise ValueError(
                f"The shortest contract on VELTRANE is {TradingRule.MIN_DURATION_SECONDS} seconds."
            )
        return self



def _config_dict(config) -> dict:
    return {
        "id": config.id,
        "connection_id": config.connection_id,
        "enabled": config.enabled,
        "mode": config.mode,
        "symbol": config.symbol,
        "contract_type": config.contract_type,
        "stake": float(config.stake),
        "duration": config.duration,
        "duration_unit": config.duration_unit,
        "max_open_contracts": config.max_open_contracts,
        "max_stake_per_trade": float(config.max_stake_per_trade),
        "daily_loss_limit": float(config.daily_loss_limit),
        "daily_stake_limit": float(config.daily_stake_limit),
        "cooldown_seconds": config.cooldown_seconds,
        "signal_ttl_seconds": config.signal_ttl_seconds,
        "universe": list(config.universe or []),
        "sector_cap": config.sector_cap,
        "last_run_at": config.last_run_at.isoformat() if config.last_run_at else None,
        "last_signal_at": config.last_signal_at.isoformat() if config.last_signal_at else None,
        "halt_reason": config.halt_reason,
    }


@router.get("/connections/{connection_id}/automation")
def get_automation(connection_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.db.models import AutoTradeConfig

    connection = _deriv_connection(db, user.org_id, connection_id)
    config = db.query(AutoTradeConfig).filter(AutoTradeConfig.connection_id == connection.id).first()
    return {"automation": _config_dict(config) if config else None}


@router.put("/connections/{connection_id}/automation")
def put_automation(
    connection_id: str,
    payload: AutomationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.db.models import AutoTradeConfig

    connection = _deriv_connection(db, user.org_id, connection_id)
    if payload.enabled:
        automation_limits.require_plan(db, user.org_id)
    if payload.enabled and payload.mode == "autonomous":
        gate = execution_gate.evaluate(db, user=user, connection=connection)
        if not gate.allowed:
            raise forbidden(
                "autonomous_mode_blocked",
                "Autonomous mode needs a fully authorised connection: " + gate.blocking_message,
                {"gate": gate.as_dict()},
            )
    config = db.query(AutoTradeConfig).filter(AutoTradeConfig.connection_id == connection.id).first()
    if config is None:
        config = AutoTradeConfig(org_id=user.org_id, connection_id=connection.id, created_by=user.id)
        db.add(config)
    for key, value in payload.model_dump().items():
        setattr(config, key, value)
    audit.record(
        db,
        action=AuditAction.AUTOTRADE_UPDATED,
        org_id=user.org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        target_type="auto_trade_config",
        target_id=config.id,
        meta=payload.model_dump(),
    )
    db.commit()
    return {"automation": _config_dict(config)}


@router.get("/connections/{connection_id}/opportunities")
def list_opportunities(
    connection_id: str,
    limit: int = Query(default=10, ge=1, le=25),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ranked setups across the venue's open symbols. Read-only: nothing is executed."""
    from app.services import opportunity_scan

    _deriv_connection(db, user.org_id, connection_id)
    adapter = deriv_sessions.adapter()
    return opportunity_scan.preview(adapter, limit=limit)


@router.get("/connections/{connection_id}/signals")
def list_signals(
    connection_id: str,
    status: str = Query(default=""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.db.models import AutoTradeSignal

    connection = _deriv_connection(db, user.org_id, connection_id)
    query = db.query(AutoTradeSignal).filter(
        AutoTradeSignal.org_id == user.org_id, AutoTradeSignal.connection_id == connection.id
    )
    if status:
        query = query.filter(AutoTradeSignal.status == status)
    rows = query.order_by(AutoTradeSignal.created_at.desc()).limit(100).all()
    return {
        "signals": [
            {
                "id": s.id,
                "status": s.status,
                "mode": s.mode,
                "symbol": s.symbol,
                "side": s.side,
                "contract_type": s.contract_type,
                "stake": float(s.stake),
                "duration": s.duration,
                "duration_unit": s.duration_unit,
                "reason": s.reason,
                "risk_snapshot": s.risk_snapshot,
                "order_id": s.order_id,
                "contract_id": s.contract_id,
                "error": s.error,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "decided_at": s.decided_at.isoformat() if s.decided_at else None,
            }
            for s in rows
        ]
    }


@router.post("/signals/{signal_id}/approve")
def approve_signal(signal_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.db.models import AutoTradeSignal
    from app.services import autotrade

    signal = db.get(AutoTradeSignal, signal_id)
    if signal is None or signal.org_id != user.org_id:
        raise not_found("signal_not_found", "Signal not found.")
    result = autotrade.execute_signal(db, signal=signal, actor=user, approved_by=user)
    db.commit()
    return result


@router.post("/signals/{signal_id}/reject")
def reject_signal(signal_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.db.models import AutoTradeSignal

    signal = db.get(AutoTradeSignal, signal_id)
    if signal is None or signal.org_id != user.org_id:
        raise not_found("signal_not_found", "Signal not found.")
    if signal.status != "pending":
        raise bad_request("signal_not_pending", f"Signal is already {signal.status}.")
    signal.status = "rejected"
    signal.decided_at = _utcnow()
    signal.decided_by = user.id
    db.commit()
    return {"status": "rejected", "signal_id": signal.id}
