"""Contract discovery: the duration menu comes from the venue, never from a constant.

The stub venue mirrors Deriv's real reply shape, including the mixed-unit bands it returns
(``15s`` to ``1d``) and a proposal engine that refuses terms it does not offer. Every
assertion here exists to prove that an unsupported duration can neither be advertised nor
executed.
"""

from __future__ import annotations

import pytest
from app.providers.base import CredentialBundle, ProviderError
from app.services import contract_catalogue

DEFAULT_ROWS = [
    {"contract_type": "CALL", "min_contract_duration": "1t", "max_contract_duration": "10t", "expiry_type": "tick"},
    {"contract_type": "CALL", "min_contract_duration": "15s", "max_contract_duration": "1d", "expiry_type": "intraday"},
    {"contract_type": "CALL", "min_contract_duration": "1d", "max_contract_duration": "365d", "expiry_type": "daily"},
    {"contract_type": "PUT", "min_contract_duration": "5t", "max_contract_duration": "10t", "expiry_type": "tick"},
    {"contract_type": "DIGITODD", "min_contract_duration": "1t", "max_contract_duration": "10t", "expiry_type": "tick"},
    {"contract_type": "CALL", "min_contract_duration": "15s", "expiry_type": "intraday"},
]


class StubVenue:
    """A venue that answers ``contracts_for`` and prices proposals the way Deriv does."""

    def __init__(self, rows=None, *, refuse=(), fail: str | None = None):
        self.rows = DEFAULT_ROWS if rows is None else rows
        self.refuse = set(refuse)
        self.fail = fail
        self.calls = 0
        self.probes: list[str] = []

    def contracts_for(self, symbol: str) -> dict:
        self.calls += 1
        if self.fail:
            raise ProviderError("venue_unreachable", self.fail)
        return {"contracts_for": {"underlying_symbol": symbol, "available": list(self.rows)}}

    def proposal(self, credentials: CredentialBundle, request: dict) -> dict:
        term = f"{request['duration']}{request['duration_unit']}"
        self.probes.append(term)
        if term in self.refuse:
            raise ProviderError("invalid_duration", f"{term} is not offered")
        return {"id": f"p-{term}", "ask_price": 10.0, "payout": 19.5}


@pytest.fixture(autouse=True)
def _clear_catalogue():
    contract_catalogue.clear_cache()
    yield
    contract_catalogue.clear_cache()


def test_parse_term_accepts_venue_units_only():
    assert contract_catalogue.parse_term("15s") == (15, "s")
    assert contract_catalogue.parse_term("1d") == (1, "d")
    assert contract_catalogue.parse_term("10t") == (10, "t")
    assert contract_catalogue.parse_term("0s") is None
    assert contract_catalogue.parse_term("15x") is None
    assert contract_catalogue.parse_term("s15") is None
    assert contract_catalogue.parse_term(None) is None


def test_tick_terms_have_no_invented_wall_clock_duration():
    assert contract_catalogue.term_seconds(5, "t") is None
    assert contract_catalogue.term_seconds(15, "s") == 15
    assert contract_catalogue.term_seconds(2, "m") == 120


def test_bands_normalise_mixed_units_and_ignore_unsupported_families():
    grouped = contract_catalogue.offers_from_contracts_for({"contracts_for": {"available": DEFAULT_ROWS}})
    assert set(grouped) == {"CALL", "PUT"}
    intraday = [band for band in grouped["CALL"] if band["unit"] == "s"]
    assert intraday == [{"unit": "s", "min": 15, "max": 86400, "expiry_type": "intraday"}]
    # The malformed row (no maximum) is dropped, not guessed at.
    assert len(grouped["CALL"]) == 3


def test_candidate_terms_stay_inside_the_published_bands():
    grouped = contract_catalogue.offers_from_contracts_for({"contracts_for": {"available": DEFAULT_ROWS}})
    terms = contract_catalogue.candidate_terms(grouped["CALL"])
    assert (15, "s") in terms and (3600, "s") in terms
    assert (1, "t") in terms and (10, "t") in terms
    assert (1, "d") in terms and (365, "d") in terms
    # No minutes band is published for CALL, so 15m is never offered.
    assert (15, "m") not in terms


def test_discover_keeps_only_terms_the_venue_prices():
    venue = StubVenue(refuse={"30s", "2t"})
    payload = contract_catalogue.discover("R_100", provider=venue)
    call_terms = payload["contracts"]["CALL"]["terms"]
    assert "15s" in call_terms
    assert "30s" not in call_terms
    assert "2t" in payload["contracts"]["CALL"]["unverified_terms"]
    assert "30s" in payload["contracts"]["CALL"]["unverified_terms"]
    assert payload["available"] is True


def test_discover_reports_unavailability_without_a_menu():
    payload = contract_catalogue.discover("R_100", provider=StubVenue(fail="socket closed"))
    assert payload["available"] is False
    assert payload["contracts"] == {}
    assert payload["error"]["code"] == "venue_unreachable"


def test_discovery_is_cached_but_unavailable_results_are_not():
    venue = StubVenue()
    contract_catalogue.get("R_100", provider=venue)
    contract_catalogue.get("R_100", provider=venue)
    assert venue.calls == 1
    contract_catalogue.get("R_100", provider=venue, refresh=True)
    assert venue.calls == 2

    contract_catalogue.clear_cache()
    broken = StubVenue(fail="timeout")
    contract_catalogue.get("R_50", provider=broken)
    contract_catalogue.get("R_50", provider=broken)
    assert broken.calls == 2


def test_terms_for_unknown_contract_type_is_empty():
    payload = contract_catalogue.discover("R_100", provider=StubVenue())
    assert contract_catalogue.terms_for(payload, "DIGITODD") == ()
    assert contract_catalogue.terms_for({"contracts": {}}, "CALL") == ()


def test_catalogue_endpoint_returns_the_venue_menu(client, trader, deriv_env):
    response = client.get("/api/v1/deriv/contracts?symbol=R_100", headers=trader["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is True
    assert body["source"] == "deriv_contracts_for"
    assert "15s" in body["contracts"]["CALL"]["terms"]
    assert "1t" in body["contracts"]["CALL"]["terms"]
    assert "DIGITODD" not in body["contracts"]


def test_catalogue_endpoint_requires_authentication(client):
    assert client.get("/api/v1/deriv/contracts?symbol=R_100").status_code == 401
