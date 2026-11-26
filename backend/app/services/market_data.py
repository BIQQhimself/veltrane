"""Market data access with an explicitly labelled synthetic fallback.

Rules:
* Real data is preferred and its provenance is always returned to the client.
* If a provider is unreachable and ``VELTRANE_DEMO_MARKET_DATA_ENABLED`` is on, a
  deterministic synthetic series is returned with ``source="demo"`` and
  ``is_demo=True``. The UI must render a DEMO badge; nothing may present it as market truth.
* Synthetic candles are reproducible: same symbol/timeframe/limit ⇒ same series.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import random
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from app.core.config import settings
from app.core.redis_client import cache_get, cache_set
from app.providers.base import Candle, ProviderError
from app.providers.registry import get_provider

log = logging.getLogger(__name__)

TIMEFRAME_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}

CRYPTO_SYMBOLS = {
    "BTC/USDT": {
        "base": "BTC",
        "quote": "USDT",
        "price": 64000.0,
        "vol": 0.018,
        "min_qty": 0.0001,
        "step": 0.0001,
        "venue": "binance",
    },
    "ETH/USDT": {
        "base": "ETH",
        "quote": "USDT",
        "price": 3200.0,
        "vol": 0.022,
        "min_qty": 0.001,
        "step": 0.001,
        "venue": "binance",
    },
    "SOL/USDT": {
        "base": "SOL",
        "quote": "USDT",
        "price": 150.0,
        "vol": 0.035,
        "min_qty": 0.01,
        "step": 0.01,
        "venue": "binance",
    },
    "BNB/USDT": {
        "base": "BNB",
        "quote": "USDT",
        "price": 580.0,
        "vol": 0.02,
        "min_qty": 0.01,
        "step": 0.01,
        "venue": "binance",
    },
    "XRP/USDT": {
        "base": "XRP",
        "quote": "USDT",
        "price": 0.62,
        "vol": 0.03,
        "min_qty": 1.0,
        "step": 1.0,
        "venue": "binance",
    },
    "ADA/USDT": {
        "base": "ADA",
        "quote": "USDT",
        "price": 0.45,
        "vol": 0.032,
        "min_qty": 1.0,
        "step": 1.0,
        "venue": "binance",
    },
}

STOCK_SYMBOLS = {
    "AAPL/USD": {
        "base": "AAPL",
        "quote": "USD",
        "price": 228.0,
        "vol": 0.011,
        "min_qty": 1.0,
        "step": 0.01,
        "asset_class": "stock",
    },
    "NVDA/USD": {
        "base": "NVDA",
        "quote": "USD",
        "price": 132.0,
        "vol": 0.021,
        "min_qty": 1.0,
        "step": 0.01,
        "asset_class": "stock",
    },
    "TSLA/USD": {
        "base": "TSLA",
        "quote": "USD",
        "price": 248.0,
        "vol": 0.024,
        "min_qty": 1.0,
        "step": 0.01,
        "asset_class": "stock",
    },
    "MSFT/USD": {
        "base": "MSFT",
        "quote": "USD",
        "price": 425.0,
        "vol": 0.010,
        "min_qty": 1.0,
        "step": 0.01,
        "asset_class": "stock",
    },
}

TRADFI_SYMBOLS = {
    "EUR/USD": {
        "base": "EUR",
        "quote": "USD",
        "price": 1.085,
        "vol": 0.004,
        "min_qty": 1000.0,
        "step": 1000.0,
        "asset_class": "forex",
    },
    "GBP/USD": {
        "base": "GBP",
        "quote": "USD",
        "price": 1.27,
        "vol": 0.005,
        "min_qty": 1000.0,
        "step": 1000.0,
        "asset_class": "forex",
    },
    "USD/JPY": {
        "base": "USD",
        "quote": "JPY",
        "price": 151.2,
        "vol": 0.005,
        "min_qty": 1000.0,
        "step": 1000.0,
        "asset_class": "forex",
    },
    "XAU/USD": {
        "base": "XAU",
        "quote": "USD",
        "price": 2320.0,
        "vol": 0.008,
        "min_qty": 1.0,
        "step": 0.1,
        "asset_class": "commodity",
    },
    "US30": {
        "base": "US30",
        "quote": "USD",
        "price": 39500.0,
        "vol": 0.007,
        "min_qty": 1.0,
        "step": 1.0,
        "asset_class": "index",
    },
}


@dataclass
class MarketSnapshot:
    symbol: str
    price: float
    bid: float | None
    ask: float | None
    ts: int
    source: str
    is_demo: bool
    age_seconds: float
    spread_bps: float | None

    def as_dict(self) -> dict:
        return asdict(self)


def instrument_spec(symbol: str) -> dict | None:
    if symbol in CRYPTO_SYMBOLS:
        spec = dict(CRYPTO_SYMBOLS[symbol])
        spec["asset_class"] = "crypto"
        return spec
    if symbol in STOCK_SYMBOLS:
        return dict(STOCK_SYMBOLS[symbol])
    if symbol in TRADFI_SYMBOLS:
        return dict(TRADFI_SYMBOLS[symbol])
    return None


def supported_symbols() -> list[dict]:
    rows = []
    for symbol, spec in CRYPTO_SYMBOLS.items():
        rows.append(
            {
                "symbol": symbol,
                "asset_class": "crypto",
                "venue": spec["venue"],
                "base": spec["base"],
                "quote": spec["quote"],
                "min_qty": spec["min_qty"],
                "qty_step": spec["step"],
                "data_source": settings.market_data_source,
            }
        )
    for symbol, spec in STOCK_SYMBOLS.items():
        rows.append(
            {
                "symbol": symbol,
                "asset_class": "stock",
                "venue": "simulated",
                "base": spec["base"],
                "quote": spec["quote"],
                "min_qty": spec["min_qty"],
                "qty_step": spec["step"],
                "data_source": "demo",
                "note": "Equity venue integration is not enabled; quotes are simulated.",
            }
        )
    for symbol, spec in TRADFI_SYMBOLS.items():
        rows.append(
            {
                "symbol": symbol,
                "asset_class": spec["asset_class"],
                "venue": "deriv",
                "base": spec["base"],
                "quote": spec["quote"],
                "min_qty": spec["min_qty"],
                "qty_step": spec["step"],
                "data_source": "demo",
                "note": "Forex/index venue integration is scaffolded; data is demo-only in this build.",
            }
        )
    return rows


def _value_noise(seed: int, ts: float, grid: int) -> float:
    """Smooth, non-periodic noise in [-1, 1] (linear grid with smoothstep easing)."""
    position = ts / grid
    left = math.floor(position)
    frac = position - left

    def sample(index: int) -> float:
        digest = hashlib.sha256(f"{seed}:{index}".encode()).digest()
        return (int.from_bytes(digest[:4], "big") / 0xFFFFFFFF) * 2 - 1

    eased = frac * frac * (3 - 2 * frac)
    return sample(left) * (1 - eased) + sample(left + 1) * eased


def _demo_price(symbol: str, ts: int, spec: dict) -> float:
    """Deterministic synthetic price for a given epoch second.

    Two slow sines give the series a trend; layered value noise supplies the
    irregular texture a real tape has. Every component is continuous in time, so
    a candle's open equals the previous close and the live quote never jumps.
    """
    seed = int(hashlib.sha256(symbol.encode()).hexdigest()[:12], 16)
    rng = random.Random(seed)
    amp1 = 0.55 + 0.45 * rng.random()
    period1 = float(rng.choice([43200, 86400, 172800]))
    phase1 = rng.random() * 2 * math.pi
    amp2 = 0.18 + 0.18 * rng.random()
    period2 = period1 / rng.choice([3, 4, 6])
    phase2 = rng.random() * 2 * math.pi
    trend = amp1 * math.sin(2 * math.pi * ts / period1 + phase1) + amp2 * math.sin(2 * math.pi * ts / period2 + phase2)
    texture = (
        0.55 * _value_noise(seed, ts, 900)
        + 0.25 * _value_noise(seed + 1, ts, 180)
        + 0.1 * _value_noise(seed + 2, ts, 45)
    )
    return spec["price"] * math.exp(spec["vol"] * 0.7 * (trend + texture))


def _demo_candles(symbol: str, timeframe: str, limit: int, now: float | None = None) -> list[Candle]:
    spec = instrument_spec(symbol) or {"price": 100.0, "vol": 0.02}
    step = TIMEFRAME_SECONDS.get(timeframe, 3600)
    current = now if now is not None else time.time()
    now_bucket = int(current // step) * step
    vol = spec["vol"] * math.sqrt(step / 3600)
    candles: list[Candle] = []
    for i in range(limit):
        start = now_bucket - (limit - 1 - i) * step
        open_ = _demo_price(symbol, start, spec)
        # The newest bar is still forming, so its close is the live price.
        close = _demo_price(symbol, int(current), spec) if i == limit - 1 else _demo_price(symbol, start + step, spec)
        # Deterministic wick size per bar so the chart looks like a market, not a line.
        bar_rng = random.Random(int(hashlib.sha256(f"{symbol}|{start}".encode()).hexdigest()[:12], 16))
        high = max(open_, close) * (1 + abs(bar_rng.gauss(0, vol / 4)))
        low = min(open_, close) * (1 - abs(bar_rng.gauss(0, vol / 4)))
        volume = abs(bar_rng.gauss(1000, 300))
        candles.append(Candle(ts=start * 1000, open=open_, high=high, low=low, close=close, volume=volume))
    return candles


def _cache_key(prefix: str, symbol: str, timeframe: str, limit: int) -> str:
    return f"md:{prefix}:{symbol}:{timeframe}:{limit}"


def price_at(symbol: str, when: datetime, timeframe: str = "1m") -> float | None:
    """Price of ``symbol`` at the instant ``when``.

    Late settlement must use the price the contract expired at, not whatever the
    market happens to be when a worker gets around to it: a worker restart would
    otherwise reprice every expired contract at the same moment.

    The demo feed is a pure function of the timestamp, so it is evaluated directly
    at any age. Real feeds are read from the finest candle that still covers the
    instant, because providers only expose a limited history per request.
    """
    spec = instrument_spec(symbol)
    if spec is None:
        return None
    if settings.market_data_source != "ccxt" or spec.get("asset_class") != "crypto":
        return float(_demo_price(symbol, int(when.timestamp()), spec))

    age_minutes = max(0.0, (time.time() - when.timestamp()) / 60)
    for candidate, span_minutes in (("1m", 1), ("5m", 5), ("15m", 15), ("1h", 60), ("4h", 240), ("1d", 1440)):
        if age_minutes / span_minutes <= 900:
            timeframe = candidate
            break
    try:
        candles, _meta = get_candles(symbol, timeframe, 1000)
    except Exception:
        return None
    target_ms = when.timestamp() * 1000
    chosen: Candle | None = None
    for candle in candles:
        if candle.ts <= target_ms:
            chosen = candle
        else:
            break
    return float(chosen.close) if chosen else None


def get_candles(symbol: str, timeframe: str = "1h", limit: int = 200) -> tuple[list[Candle], dict]:
    spec = instrument_spec(symbol)
    if spec is None:
        from app.core.errors import not_found

        raise not_found("instrument_not_found", f"Instrument '{symbol}' is not supported.")
    if timeframe not in TIMEFRAME_SECONDS:
        from app.core.errors import bad_request

        raise bad_request("unsupported_timeframe", f"Timeframe '{timeframe}' is not supported.")
    limit = max(20, min(int(limit), 1000))

    if settings.market_data_source == "ccxt" and spec.get("asset_class") == "crypto":
        cached = cache_get(_cache_key("candles", symbol, timeframe, limit))
        if cached:
            payload = json.loads(cached)
            return [Candle(**row) for row in payload["rows"]], payload["meta"]
        try:
            provider = get_provider(spec["venue"])
            candles = provider.fetch_ohlcv(symbol, timeframe, limit)
            meta = {"source": f"ccxt:{spec['venue']}", "is_demo": False, "fetched_at": int(time.time())}
            cache_set(
                _cache_key("candles", symbol, timeframe, limit),
                json.dumps({"rows": [asdict(c) for c in candles], "meta": meta}),
                settings.market_data_cache_seconds,
            )
            return candles, meta
        except (ProviderError, Exception) as exc:  # noqa: BLE001 - fall through to demo feed
            log.warning("market_data_fallback", extra={"extra_fields": {"symbol": symbol, "error": str(exc)[:200]}})

    if not settings.demo_market_data_enabled:
        from app.core.errors import AppError

        raise AppError(503, "market_data_unavailable", "Live market data is unavailable and the demo feed is disabled.")
    return _demo_candles(symbol, timeframe, limit), {
        "source": "demo",
        "is_demo": True,
        "note": "Synthetic data generated by VELTRANE for demonstration. Not real market data.",
        "fetched_at": int(time.time()),
    }


def get_ticker(symbol: str) -> MarketSnapshot:
    spec = instrument_spec(symbol)
    if spec is None:
        from app.core.errors import not_found

        raise not_found("instrument_not_found", f"Instrument '{symbol}' is not supported.")
    if settings.market_data_source == "ccxt" and spec.get("asset_class") == "crypto":
        cached = cache_get(f"md:ticker:{symbol}")
        if cached:
            payload = json.loads(cached)
            return MarketSnapshot(**payload)
        try:
            provider = get_provider(spec["venue"])
            ticker = provider.fetch_ticker(symbol)
            spread_bps = None
            if ticker.bid and ticker.ask:
                spread_bps = (ticker.ask - ticker.bid) / ticker.price * 10_000
            snap = MarketSnapshot(
                symbol=symbol,
                price=ticker.price,
                bid=ticker.bid,
                ask=ticker.ask,
                ts=ticker.ts or int(time.time() * 1000),
                source=ticker.source,
                is_demo=False,
                age_seconds=max(0.0, time.time() - (ticker.ts or time.time() * 1000) / 1000),
                spread_bps=spread_bps,
            )
            cache_set(f"md:ticker:{symbol}", json.dumps(snap.as_dict()), settings.market_data_cache_seconds)
            return snap
        except Exception as exc:  # noqa: BLE001
            log.warning("ticker_fallback", extra={"extra_fields": {"symbol": symbol, "error": str(exc)[:200]}})

    if not settings.demo_market_data_enabled:
        from app.core.errors import AppError

        raise AppError(503, "market_data_unavailable", "Live market data is unavailable and the demo feed is disabled.")
    price = _demo_price(symbol, int(time.time()), spec)
    spread_bps = 3.0 if spec.get("asset_class") == "crypto" else 1.5
    half = price * spread_bps / 20_000
    return MarketSnapshot(
        symbol=symbol,
        price=price,
        bid=price - half,
        ask=price + half,
        ts=int(time.time() * 1000),
        source="demo",
        is_demo=True,
        age_seconds=0.0,
        spread_bps=spread_bps,
    )


def is_market_open(symbol: str, now: datetime | None = None) -> bool:
    spec = instrument_spec(symbol)
    if spec is None:
        return False
    if spec.get("asset_class") == "crypto":
        return True
    now = now or datetime.now(UTC)
    # Retail forex/indices: closed from Friday 21:00 UTC to Sunday 21:00 UTC.
    weekday = now.weekday()  # Mon=0
    if weekday == 5:
        return False
    if weekday == 4 and now.hour >= 21:
        return False
    if weekday == 6 and now.hour < 21:
        return False
    return True
