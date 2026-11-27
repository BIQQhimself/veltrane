"""Deriv adapter: authentication, identity, pricing, execution and reconnection.

Authenticated flows run against ``tests/support/deriv_mock.py`` — a local server that implements
Deriv's documented REST + WebSocket protocol. Public market data is covered by
``test_deriv_live_market_data.py``, which talks to the real gateway and is skipped when the
sandbox has no outbound network access.
"""

from __future__ import annotations

import time

import pytest
from app.providers.base import CredentialBundle, ProviderError
from app.providers.deriv import DerivProvider
from app.providers.deriv_client import DerivError, DerivREST, DerivTradingSession
from tests.support.deriv_mock import MockDerivServer


@pytest.fixture(scope="module")
def mock_deriv():
    server = MockDerivServer().start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture()
def state(mock_deriv):
    mock_deriv.state.reset()
    return mock_deriv.state


@pytest.fixture()
def provider(mock_deriv):
    return DerivProvider(
        rest_base=mock_deriv.base_url,
        public_ws_url=mock_deriv.public_ws_url,
        default_app_id=mock_deriv.state.app_id,
    )


def creds(state, *, account_id="", app_id=None) -> CredentialBundle:
    return CredentialBundle(
        api_key=state.token,
        app_id=state.app_id if app_id is None else app_id,
        account_id=account_id,
    )


# ------------------------------------------------------------------ authentication
def test_pat_authenticates_and_reports_identity(provider, state):
    result = provider.test_connection(creds(state))

    assert result["ok"] is True
    assert result["app_id"] == state.app_id
    assert result["token_kind"] == "pat"
    assert len(result["accounts"]) == 2
    # The demo account is selected when the caller has not chosen one.
    assert result["account_id"] == "VRTC900001"
    assert result["account_type"] == "demo"
    assert result["is_virtual"] is True
    assert result["balance"] == 10000.0
    assert result["currency"] == "USD"
    # No secret is ever part of the result.
    assert state.token not in str(result)


def test_wrong_app_id_is_rejected_by_deriv(provider, state):
    with pytest.raises(ProviderError) as excinfo:
        provider.test_connection(creds(state, app_id="99999"))

    assert excinfo.value.code == "deriv_app_id_required"
    assert "Deriv-App-ID" in excinfo.value.message


def test_missing_app_id_fails_before_a_round_trip(mock_deriv, state):
    no_default = DerivProvider(rest_base=mock_deriv.base_url, default_app_id="")
    before = state.otp_requests

    with pytest.raises(ProviderError) as excinfo:
        no_default.test_connection(CredentialBundle(api_key=state.token, app_id=""))

    assert excinfo.value.code == "app_id_required"
    assert state.otp_requests == before


def test_invalid_token_is_reported_precisely(provider, state):
    state.reject_token = True
    with pytest.raises(ProviderError) as excinfo:
        provider.test_connection(creds(state))

    assert excinfo.value.code == "deriv_invalid_token"
    assert "token" in excinfo.value.message.lower()


def test_malformed_token_is_rejected_without_a_round_trip(provider, state):
    before = state.otp_requests
    with pytest.raises(ProviderError) as excinfo:
        provider.test_connection(CredentialBundle(api_key="abc", app_id=state.app_id))

    assert excinfo.value.code == "token_malformed"
    assert state.otp_requests == before


def test_real_account_is_identified(provider, state):
    result = provider.test_connection(creds(state, account_id="CR700001"))

    assert result["account_type"] == "real"
    assert result["is_virtual"] is False
    assert result["balance"] == 250.0


def test_balances_cover_every_account(provider, state):
    rows = provider.fetch_balances(creds(state))

    assert len(rows) == 2
    demo = next(row for row in rows if row["meta"]["account_id"] == "VRTC900001")
    assert demo["total"] == 10000.0
    assert demo["usd_value"] == 10000.0


# ------------------------------------------------------------------ market data and pricing
def test_active_symbols_and_ticker(provider):
    symbols = provider.active_symbols()
    assert {row["underlying_symbol"] for row in symbols} == {"R_100", "frxEURUSD"}

    ticker = provider.fetch_ticker("R_100")
    assert ticker.price > 0
    assert ticker.source == "deriv"


def test_candles_are_mapped(provider):
    candles = provider.fetch_ohlcv("R_100", "1m", 3)
    assert len(candles) == 3
    assert candles[0].high >= candles[0].low


def test_forex_bars_are_bucketed_from_ticks(monkeypatch):
    """Deriv serves ticks but no candles for forex; the adapter must not return an empty series."""
    from app.providers import deriv as deriv_module

    calls: list[dict] = []

    def fake_fetch_public(payload, timeout=None, url=None):
        calls.append(payload)
        if payload.get("style") == "candles":
            return {"msg_type": "candles", "candles": []}
        return {
            "msg_type": "history",
            "history": {
                "prices": [1.1000, 1.1040, 1.0980, 1.1010, 1.1020],
                "times": [600, 660, 720, 900, 960],
            },
        }

    monkeypatch.setattr(deriv_module, "fetch_public", fake_fetch_public)
    candles = DerivProvider().fetch_ohlcv("frxEURUSD", "5m", 3)

    assert [c.ts for c in candles] == [600, 900]
    assert (candles[0].open, candles[0].high, candles[0].low, candles[0].close) == (1.1, 1.104, 1.098, 1.098)
    assert (candles[1].open, candles[1].close) == (1.101, 1.102)
    assert all(c.volume == 0.0 for c in candles)
    assert calls[1]["style"] == "ticks"


def test_proposal_uses_underlying_symbol(provider, state):
    proposal = provider.proposal(creds(state), {"symbol": "R_100", "stake": 10, "side": "buy", "duration": 5})
    assert proposal["id"]
    assert proposal["ask_price"] == 10.0


# ------------------------------------------------------------------ execution
def _session(provider, state, account_id="VRTC900001", *, max_failures=5) -> DerivTradingSession:
    return DerivTradingSession(
        rest=DerivREST(state.token, app_id=state.app_id, base_url=provider.rest_base),
        account_id=account_id,
        account_type="demo",
        currency="USD",
        max_consecutive_failures=max_failures,
    )


def test_demo_buy_then_sell(provider, state):
    session = _session(provider, state)
    try:
        session.connect()
        checks = session.resume_checks(allowed=True)
        assert checks["resumed"] is True, checks

        buy = provider.place_order(
            creds(state),
            {"symbol": "R_100", "side": "buy", "stake": 10, "duration": 5},
            session=session,
        )
        sell = provider.cancel_order(creds(state), buy["provider_order_id"], session=session)
    finally:
        session.close()

    assert buy["status"] == "filled"
    assert buy["is_demo"] is True
    assert buy["provider_order_id"]
    assert buy["avg_fill_price"] == 10.0
    assert buy["contract_type"] == "CALL"
    assert sell["status"] == "sold"
    assert sell["sold_for"] > 0


def test_paused_session_refuses_to_trade(provider, state):
    session = _session(provider, state)
    try:
        session.connect()
        # No resume_checks: the session is still paused after connecting.
        with pytest.raises(ProviderError) as excinfo:
            provider.place_order(
                creds(state),
                {"symbol": "R_100", "side": "buy", "stake": 10},
                session=session,
            )
    finally:
        session.close()

    assert excinfo.value.code == "session_paused"


def test_open_contracts_and_positions(provider, state):
    session = _session(provider, state)
    try:
        session.connect()
        session.resume_checks(allowed=True)
        provider.place_order(creds(state), {"symbol": "R_100", "side": "buy", "stake": 5}, session=session)
        contracts = provider.open_contracts(creds(state, account_id="VRTC900001"), session=session)
        positions = provider.fetch_positions(creds(state, account_id="VRTC900001"), session=session)
    finally:
        session.close()

    assert len(contracts) == 1
    assert positions[0]["symbol"] == "R_100"
    assert positions[0]["side"] == "long"


def test_session_reconnects_after_the_socket_drops(provider, state):
    state.drop_after_buys = 1
    session = _session(provider, state)
    try:
        session.connect()
        session.resume_checks(allowed=True)
        provider.place_order(creds(state), {"symbol": "R_100", "side": "buy", "stake": 5}, session=session)
        for _ in range(100):
            if not session.connected:
                break
            time.sleep(0.05)
        assert session.connected is False

        reconnect = session.reconnect(attempts=3)
        checks = session.resume_checks(allowed=True)
        portfolio = session.request({"portfolio": 1})
    finally:
        session.close()

    assert reconnect["connected"] is True
    assert checks["resumed"] is True
    # The contract opened before the drop is still visible after reconnecting.
    assert len((portfolio.get("portfolio") or {}).get("contracts") or []) == 1
    assert state.otp_requests >= 2


def test_reconnect_backoff_gives_up_and_suspends(provider, state):
    state.otp_failures = 50
    session = _session(provider, state, max_failures=3)
    try:
        with pytest.raises(DerivError):
            session.reconnect(attempts=3)
        assert session.state.suspended is True
        assert session.state.consecutive_failures >= 3
        assert session.trading_paused is True
        checks = session.resume_checks(allowed=True)
    finally:
        session.close()

    assert checks["resumed"] is False


def test_resume_requires_authorisation(provider, state):
    session = _session(provider, state)
    try:
        session.connect()
        result = session.resume_checks(allowed=False)
    finally:
        session.close()

    assert result["resumed"] is False
    assert any(item["check"] == "authorization_active" and not item["ok"] for item in result["checks"])
