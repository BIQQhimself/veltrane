from __future__ import annotations

from app.services import market_data


def test_demo_candles_are_continuous():
    candles = market_data._demo_candles("BTC/USDT", "5m", 40, now=1_800_000_000)
    assert len(candles) == 40
    for previous, current in zip(candles, candles[1:], strict=False):
        assert current.open == previous.close
        assert current.ts - previous.ts == 5 * 60 * 1000
        assert current.high >= max(current.open, current.close)
        assert current.low <= min(current.open, current.close)


def test_demo_candles_are_reproducible_for_the_same_instant():
    first = market_data._demo_candles("ETH/USDT", "1m", 20, now=1_800_000_000)
    second = market_data._demo_candles("ETH/USDT", "1m", 20, now=1_800_000_000)
    assert [c.close for c in first] == [c.close for c in second]


def test_demo_price_moves_between_buckets():
    spec = market_data.instrument_spec("BTC/USDT")
    assert spec is not None
    one = market_data._demo_candles("BTC/USDT", "1m", 2, now=1_800_000_000)
    later = market_data._demo_candles("BTC/USDT", "1m", 2, now=1_800_000_060)
    assert one[-1].close != later[-1].close, "the synthetic feed must not be frozen"
    assert one[-1].close == market_data._demo_price("BTC/USDT", 1_800_000_000, spec)
    assert later[0].open == one[-1].close, "consecutive windows must line up"


def test_demo_price_stays_within_a_plausible_band():
    spec = market_data.instrument_spec("BTC/USDT")
    assert spec is not None
    for offset in range(0, 86_400, 600):
        price = market_data._demo_price("BTC/USDT", 1_800_000_000 + offset, spec)
        assert spec["price"] * 0.5 < price < spec["price"] * 2.0


def test_price_at_returns_a_stable_historical_close():
    from datetime import UTC, datetime, timedelta

    when = datetime.now(UTC) - timedelta(minutes=20)
    first = market_data.price_at("BTC/USDT", when)
    second = market_data.price_at("BTC/USDT", when)
    assert first is not None and first > 0
    assert first == second


def test_price_at_is_unknown_for_an_unsupported_instrument():
    from datetime import UTC, datetime

    assert market_data.price_at("NOT/A/PAIR", datetime.now(UTC)) is None
