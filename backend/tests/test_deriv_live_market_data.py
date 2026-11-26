"""Deriv public market data, against the real gateway.

These calls need no credentials: they hit ``wss://api.derivws.com/trading/v1/options/ws/public``.
They are skipped when the machine has no outbound access to Deriv, so the suite stays green on an
isolated runner while still proving the integration on a networked one.
"""

from __future__ import annotations

import pytest
from app.providers.base import ProviderError
from app.providers.deriv import DerivProvider
from app.providers.deriv_client import DerivError, fetch_public

pytestmark = pytest.mark.deriv_live


def _reachable() -> bool:
    try:
        fetch_public({"ping": 1}, timeout=8)
        return True
    except (DerivError, OSError):
        return False


LIVE = _reachable()
skip_unless_live = pytest.mark.skipif(not LIVE, reason="Deriv gateway not reachable from this host")


@skip_unless_live
def test_ping_round_trip():
    payload = fetch_public({"ping": 1})
    assert payload.get("ping") == "pong"


@skip_unless_live
def test_active_symbols_include_forex_and_synthetics():
    symbols = DerivProvider().active_symbols()
    assert len(symbols) > 10
    markets = {row.get("market") for row in symbols}
    assert "synthetic_index" in markets
    assert "forex" in markets
    assert all(row.get("underlying_symbol") for row in symbols)


@skip_unless_live
def test_live_ticker_and_candles():
    provider = DerivProvider()
    ticker = provider.fetch_ticker("R_100")
    assert ticker.price > 0

    candles = provider.fetch_ohlcv("R_100", "1m", 5)
    assert len(candles) == 5
    for candle in candles:
        assert candle.low <= candle.open <= candle.high
        assert candle.low <= candle.close <= candle.high


@skip_unless_live
def test_live_forex_candles():
    candles = DerivProvider().fetch_ohlcv("frxEURUSD", "5m", 3)
    assert len(candles) == 3
    assert 0.5 < candles[-1].close < 2.0


@skip_unless_live
def test_live_contract_proposal():
    from app.providers.base import CredentialBundle

    proposal = DerivProvider().proposal(
        CredentialBundle(),
        {"symbol": "R_100", "stake": 10, "side": "buy", "duration": 5, "currency": "USD"},
    )
    assert proposal["id"]
    assert proposal["ask_price"] == 10.0
    assert proposal["payout"] > 10.0


@skip_unless_live
def test_unknown_symbol_is_rejected_not_faked():
    provider = DerivProvider()
    with pytest.raises(ProviderError):
        provider.fetch_ohlcv("NOT_A_SYMBOL", "1m", 2)
