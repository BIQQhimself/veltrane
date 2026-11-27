"""Which contracts and durations the venue actually offers, discovered at runtime.

Nothing in this module is a hardcoded capability list. The menu is built from Deriv's own
``contracts_for`` response, and every duration that survives into the menu has been accepted
by Deriv's proposal engine for that symbol. A duration the venue refuses is dropped, never
rounded to a neighbour and never filled in from a constant.

Two consequences worth stating plainly:

* When discovery fails the catalogue is reported as unavailable. Callers must show that,
  not substitute a default list.
* Caching is short-lived (``TTL_SECONDS``) because Deriv changes contract availability per
  symbol without notice; a stale menu is a bug, not a feature.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.redis_client import get_json, set_json
from app.providers.base import CredentialBundle, ProviderError

log = logging.getLogger(__name__)

TTL_SECONDS = 600
MAX_PROPOSALS = 40
PROBE_STAKE = 1.0

# Ladders are candidate menus, not claims: each entry is offered only if the venue's
# contracts_for range admits it *and* a live proposal accepts it.
LADDERS: dict[str, tuple[int, ...]] = {
    "t": (1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
    "s": (15, 30, 45, 60, 90, 120, 180, 300, 600, 900, 1800, 3600),
    "m": (1, 2, 3, 5, 10, 15, 30, 60, 120, 240, 480, 720, 1440),
    "h": (1, 2, 3, 6, 12, 24),
    "d": (1, 2, 3, 5, 7, 14, 30, 60, 90, 180, 365),
}

UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}

# The terminal and the agent both trade up/down contracts. Other families (digits,
# touch/no-touch, multipliers) are surfaced by Deriv but are not implemented, so they are
# not advertised here.
SUPPORTED_CONTRACT_TYPES = ("CALL", "PUT")

_LOCK = threading.Lock()
_MEMORY: dict[str, dict[str, Any]] = {}


def _now() -> datetime:
    return datetime.now(UTC)


def _key(symbol: str) -> str:
    return f"contract_catalogue:{symbol}"


def _cache_get(symbol: str) -> dict[str, Any] | None:
    cached = get_json(_key(symbol))
    if cached is None:
        with _LOCK:
            cached = _MEMORY.get(symbol)
    if not cached:
        return None
    try:
        fetched = datetime.fromisoformat(cached["fetched_at"])
    except (KeyError, TypeError, ValueError):
        return None
    if fetched + timedelta(seconds=TTL_SECONDS) < _now():
        return None
    return cached


def _cache_set(symbol: str, payload: dict[str, Any]) -> None:
    set_json(_key(symbol), payload, TTL_SECONDS)
    with _LOCK:
        _MEMORY[symbol] = payload


def clear_cache(symbol: str | None = None) -> None:
    with _LOCK:
        if symbol:
            _MEMORY.pop(symbol, None)
        else:
            _MEMORY.clear()


def parse_term(text: str | None) -> tuple[int, str] | None:
    """``"15s"`` -> ``(15, "s")``; ``"1d"`` -> ``(1, "d")``. Anything else is None."""
    if not text:
        return None
    body = str(text).strip().lower()
    if len(body) < 2 or body[-1] not in LADDERS:
        return None
    try:
        value = int(body[:-1])
    except ValueError:
        return None
    return (value, body[-1]) if value > 0 else None


def term_seconds(value: int, unit: str) -> int | None:
    """Wall-clock seconds for a term, or None when the venue defines the length (ticks)."""
    multiplier = UNIT_SECONDS.get(unit)
    return value * multiplier if multiplier else None


def term_label(value: int, unit: str) -> str:
    names = {"t": "tick", "s": "sec", "m": "min", "h": "hour", "d": "day"}
    plural = names.get(unit, unit)
    return f"{value} {plural}" + ("" if value == 1 else "s")


def _band(low: tuple[int, str], high: tuple[int, str]) -> dict[str, Any] | None:
    """Normalise a min/max pair onto the min's unit.

    Deriv mixes units in one band — ``min_contract_duration: "15s"`` with
    ``max_contract_duration: "1d"`` is the normal shape for intraday contracts — so the
    maximum is converted into the minimum's unit rather than the band being discarded.
    """
    if low[1] == high[1]:
        return {"unit": low[1], "min": low[0], "max": high[0]}
    low_factor = UNIT_SECONDS.get(low[1])
    high_factor = UNIT_SECONDS.get(high[1])
    if not low_factor or not high_factor or high_factor < low_factor:
        return None
    return {"unit": low[1], "min": low[0], "max": int(high[0] * high_factor // low_factor)}


def offers_from_contracts_for(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Group Deriv's ``contracts_for.available`` rows into duration bands per contract type."""
    rows = ((payload or {}).get("contracts_for") or {}).get("available") or []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        contract_type = str(row.get("contract_type") or "").upper()
        if contract_type not in SUPPORTED_CONTRACT_TYPES:
            continue
        low = parse_term(row.get("min_contract_duration"))
        high = parse_term(row.get("max_contract_duration"))
        if not low or not high:
            continue
        band = _band(low, high)
        if band is None or band["max"] < band["min"]:
            continue
        grouped.setdefault(contract_type, []).append({**band, "expiry_type": row.get("expiry_type")})
    return grouped


def candidate_terms(bands: list[dict[str, Any]]) -> list[tuple[int, str]]:
    """Every ladder entry that falls inside a band the venue published, deduplicated."""
    seen: dict[tuple[int, str], None] = {}
    for band in bands:
        unit = band["unit"]
        for value in LADDERS.get(unit, ()):
            if band["min"] <= value <= band["max"]:
                seen[(value, unit)] = None
    return list(seen)


def _verify(provider, symbol: str, currency: str, terms: list[tuple[int, str]]) -> list[str]:
    accepted: list[str] = []
    for value, unit in terms[:MAX_PROPOSALS]:
        try:
            provider.proposal(
                CredentialBundle(),
                {
                    "symbol": symbol,
                    "stake": PROBE_STAKE,
                    "side": "buy",
                    "contract_type": "CALL",
                    "duration": value,
                    "duration_unit": unit,
                    "currency": currency,
                },
            )
        except ProviderError:
            continue
        except Exception:  # noqa: BLE001 - a discovery probe must never break a request
            log.warning("contract probe failed for %s %s%s", symbol, value, unit, exc_info=True)
            continue
        accepted.append(f"{value}{unit}")
    return accepted


def discover(symbol: str, currency: str = "USD", *, provider, verify: bool = True) -> dict[str, Any]:
    """Ask the venue what it offers for ``symbol`` and cache the answer."""
    try:
        payload = provider.contracts_for(symbol)
    except ProviderError as exc:
        return {
            "symbol": symbol,
            "currency": currency,
            "available": False,
            "source": "deriv_contracts_for",
            "fetched_at": _now().isoformat(),
            "error": {"code": exc.code, "message": exc.message},
            "contracts": {},
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("contracts_for failed for %s", symbol, exc_info=True)
        return {
            "symbol": symbol,
            "currency": currency,
            "available": False,
            "source": "deriv_contracts_for",
            "fetched_at": _now().isoformat(),
            "error": {"code": "venue_unreachable", "message": str(exc)},
            "contracts": {},
        }

    grouped = offers_from_contracts_for(payload)
    contracts: dict[str, dict[str, Any]] = {}
    for contract_type in SUPPORTED_CONTRACT_TYPES:
        bands = grouped.get(contract_type) or []
        terms = candidate_terms(bands)
        if not terms:
            continue
        verified = _verify(provider, symbol, currency, terms) if verify else [f"{v}{u}" for v, u in terms]
        contracts[contract_type] = {
            "terms": verified,
            "unverified_terms": [f"{v}{u}" for v, u in terms if f"{v}{u}" not in verified],
            "bands": bands,
        }

    return {
        "symbol": symbol,
        "currency": currency,
        "available": bool(contracts),
        "source": "deriv_contracts_for",
        "verified": verify,
        "fetched_at": _now().isoformat(),
        "expires_at": (_now() + timedelta(seconds=TTL_SECONDS)).isoformat(),
        "contracts": contracts,
    }


def get(symbol: str, currency: str = "USD", *, provider, refresh: bool = False) -> dict[str, Any]:
    """Cached catalogue for one symbol. Never returns an invented menu."""
    if not refresh:
        cached = _cache_get(symbol)
        if cached is not None:
            return cached
    payload = discover(symbol, currency, provider=provider)
    if payload.get("available"):
        _cache_set(symbol, payload)
    return payload


def terms_for(catalogue: dict[str, Any], contract_type: str) -> tuple[str, ...]:
    """Verified terms for a contract type, or an empty tuple when nothing is known."""
    entry = (catalogue.get("contracts") or {}).get(contract_type.upper()) or {}
    return tuple(entry.get("terms") or ())
