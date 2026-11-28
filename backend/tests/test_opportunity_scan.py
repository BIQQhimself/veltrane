"""The market-wide opportunity scanner: ranking, caps and honest idling."""

from __future__ import annotations

import math

from app.providers.base import Candle, ProviderError
from app.services import opportunity_scan as scan


def series(closes: list[float], *, spread: float = 0.001) -> list[Candle]:
    return [
        Candle(ts=i * 60, open=close, high=close * (1 + spread), low=close * (1 - spread), close=close, volume=1.0)
        for i, close in enumerate(closes)
    ]


def wave(length: int = 80) -> list[float]:
    return [round(100 + 2 * math.sin(math.radians(170) + 2 * math.pi * i / 14), 2) for i in range(length)]


def uptrend(length: int = 80) -> list[float]:
    return [100 + 0.05 * i for i in range(length)]


def downtrend(length: int = 80) -> list[float]:
    return [120 - 0.05 * i for i in range(length)]


def test_a_steady_uptrend_is_ranked_as_a_call():
    opportunity = scan.evaluate(series(uptrend()), symbol="R_100", sector="synthetic_index")
    assert opportunity is not None
    assert opportunity.contract_type == "CALL"
    assert opportunity.side == "buy"
    assert opportunity.score >= scan.MIN_SCORE


def test_a_steady_downtrend_is_ranked_as_a_put():
    opportunity = scan.evaluate(series(downtrend()), symbol="frxEURUSD", sector="forex")
    assert opportunity is not None
    assert opportunity.contract_type == "PUT"
    assert opportunity.side == "sell"


def test_directions_are_scored_independently():
    up_call, _ = scan.score_direction(series(uptrend()), "CALL")
    up_put, _ = scan.score_direction(series(uptrend()), "PUT")
    assert up_call > up_put
    down_put, _ = scan.score_direction(series(downtrend()), "PUT")
    down_call, _ = scan.score_direction(series(downtrend()), "CALL")
    assert down_put > down_call


def test_a_noisy_series_is_not_traded():
    """The scanner must idle rather than manufacture a setup out of chop."""
    assert scan.evaluate(series(wave()), symbol="R_100", sector="synthetic_index") is None


def test_a_flat_series_is_not_traded():
    assert scan.evaluate(series([100.0] * 80)) is None


def test_a_short_series_is_ignored():
    assert scan.evaluate(series(uptrend(20))) is None
    assert scan.score_direction(series(uptrend(20)), "CALL") is None


def test_scores_stay_inside_the_documented_range():
    for closes in (uptrend(), downtrend(), wave()):
        for direction in ("CALL", "PUT"):
            score, parts = scan.score_direction(series(closes), direction)
            assert 0.0 <= score <= 100.0
            assert set(parts["components"]) == set(scan.WEIGHTS)


def _opportunity(symbol: str, sector: str, score: float) -> scan.Opportunity:
    return scan.Opportunity(symbol=symbol, sector=sector, contract_type="CALL", score=score, reason="")


def test_select_takes_the_strongest_first_and_stops_at_the_slot_count():
    ranked = [
        _opportunity("A", "synthetic_index", 90),
        _opportunity("B", "forex", 80),
        _opportunity("C", "commodities", 70),
    ]
    picked = scan.select(ranked, slots=2, sector_cap=2)
    assert [item.symbol for item in picked] == ["A", "B"]


def test_select_enforces_the_sector_cap():
    ranked = [
        _opportunity("R_10", "synthetic_index", 90),
        _opportunity("R_25", "synthetic_index", 85),
        _opportunity("frxEURUSD", "forex", 60),
    ]
    picked = scan.select(ranked, slots=3, sector_cap=1)
    assert [item.symbol for item in picked] == ["R_10", "frxEURUSD"]


def test_select_never_repeats_a_symbol_already_held():
    ranked = [_opportunity("R_100", "synthetic_index", 90), _opportunity("frxEURUSD", "forex", 80)]
    picked = scan.select(ranked, slots=2, exclude_symbols={"R_100"})
    assert [item.symbol for item in picked] == ["frxEURUSD"]


def test_select_with_no_free_capacity_picks_nothing():
    assert scan.select([_opportunity("R_100", "synthetic_index", 99)], slots=0) == []


class FakeAdapter:
    def __init__(self, symbols: list[dict], candles: dict[str, list[float]], broken: set[str] | None = None):
        self._symbols = symbols
        self._candles = candles
        self._broken = broken or set()
        self.fetched: list[str] = []

    def active_symbols(self) -> list[dict]:
        return self._symbols

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        self.fetched.append(symbol)
        if symbol in self._broken:
            raise ProviderError("venue_error", "boom")
        return series(self._candles[symbol])


def _row(symbol: str, market: str, *, open_: int = 1, suspended: int = 0) -> dict:
    return {
        "underlying_symbol": symbol,
        "underlying_symbol_name": symbol,
        "market": market,
        "exchange_is_open": open_,
        "is_trading_suspended": suspended,
    }


def test_scan_ranks_across_sectors_and_survives_one_broken_symbol():
    adapter = FakeAdapter(
        [_row("R_100", "synthetic_index"), _row("frxEURUSD", "forex"), _row("frxUSDJPY", "forex")],
        {"R_100": uptrend(), "frxEURUSD": downtrend(), "frxUSDJPY": uptrend()},
        broken={"frxUSDJPY"},
    )
    found, stats = scan.scan(adapter)
    assert stats == {"scanned": 3, "skipped": 1, "universe": 3}
    assert {item.symbol for item in found} == {"R_100", "frxEURUSD"}
    assert found[0].score >= found[1].score


def test_scan_ignores_closed_and_suspended_markets():
    adapter = FakeAdapter(
        [
            _row("R_100", "synthetic_index", open_=0),
            _row("frxEURUSD", "forex", suspended=1),
            _row("frxAUDUSD", "forex"),
        ],
        {"R_100": uptrend(), "frxEURUSD": uptrend(), "frxAUDUSD": uptrend()},
    )
    found, stats = scan.scan(adapter)
    assert stats["universe"] == 1
    assert adapter.fetched == ["frxAUDUSD"]
    assert [item.symbol for item in found] == ["frxAUDUSD"]


def test_scan_can_be_restricted_to_an_explicit_universe():
    adapter = FakeAdapter(
        [_row("R_100", "synthetic_index"), _row("frxEURUSD", "forex")],
        {"R_100": uptrend(), "frxEURUSD": uptrend()},
    )
    found, _ = scan.scan(adapter, symbols=["frxEURUSD"])
    assert adapter.fetched == ["frxEURUSD"]
    assert [item.symbol for item in found] == ["frxEURUSD"]


def test_scan_reports_an_unavailable_universe_instead_of_inventing_one():
    class Down:
        def active_symbols(self):
            raise ProviderError("venue_down", "no route")

        def fetch_ohlcv(self, *args, **kwargs):
            raise AssertionError("must not be called")

    found, stats = scan.scan(Down())
    assert found == []
    assert "universe unavailable" in stats["error"]


def test_preview_returns_a_read_only_ranking():
    adapter = FakeAdapter(
        [_row("R_100", "synthetic_index"), _row("frxEURUSD", "forex")],
        {"R_100": uptrend(), "frxEURUSD": downtrend()},
    )
    payload = scan.preview(adapter, limit=5)
    assert payload["qualifying"] == 2
    assert payload["scanned"] == 2
    assert [row["symbol"] for row in payload["opportunities"]] == ["R_100", "frxEURUSD"]
    assert payload["opportunities"][0]["contract_type"] == "CALL"
    assert payload["opportunities"][1]["contract_type"] == "PUT"
    assert "no profitability claim" in payload["opportunities"][0]["reason"]
