from __future__ import annotations

from app.core.config import settings
from app.core.rate_limit import enforce
from app.services import market_data
from fastapi import APIRouter, Request

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("/instruments")
def instruments():
    return {
        "instruments": market_data.supported_symbols(),
        "data_source_mode": settings.market_data_source,
        "demo_feed_enabled": settings.demo_market_data_enabled,
    }


@router.get("/ticker/{symbol:path}")
def ticker(symbol: str, request: Request):
    enforce(request, "ticker", limit=120, window=60)
    snapshot = market_data.get_ticker(symbol)
    return snapshot.as_dict()


@router.get("/candles/{symbol:path}")
def candles(symbol: str, timeframe: str = "1h", limit: int = 200, request: Request = None):
    if request:
        enforce(request, "candles", limit=120, window=60)
    rows, meta = market_data.get_candles(symbol, timeframe, limit)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "meta": meta,
        "candles": [
            {"ts": c.ts, "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
            for c in rows
        ],
    }


@router.get("/summary")
def summary(request: Request):
    enforce(request, "summary", limit=60, window=60)
    out = []
    for item in market_data.supported_symbols():
        try:
            snap = market_data.get_ticker(item["symbol"])
            out.append(
                {
                    **item,
                    "price": snap.price,
                    "change_hint": None,
                    "is_demo": snap.is_demo,
                    "source": snap.source,
                    "market_open": market_data.is_market_open(item["symbol"]),
                }
            )
        except Exception as exc:  # noqa: BLE001 - one bad symbol must not break the page
            out.append({**item, "price": None, "error": str(exc)[:160], "is_demo": True})
    return {"markets": out, "data_source_mode": settings.market_data_source}
