"""The one-minute floor, asserted at every boundary that could bypass it.

The floor is a product rule, not a venue capability: Deriv prices 1-tick and 15-second
contracts and the platform still refuses them. These tests exist so that a future change to
the catalogue, a request model or the agent cannot quietly reintroduce a sub-minute path.
"""

from __future__ import annotations

import pytest
from app.db.constants import TradingRule
from app.services import contract_catalogue
from app.trading import binary


def test_the_floor_has_a_single_definition():
    assert TradingRule.MIN_DURATION_SECONDS == 60
    # The paper book re-exports the constant rather than declaring its own copy.
    assert binary.MIN_DURATION_SECONDS == TradingRule.MIN_DURATION_SECONDS


@pytest.mark.parametrize("term", ["1t", "5t", "10t", "15s", "30s", "45s", "59s"])
def test_terms_below_the_floor_are_untradeable(term):
    assert contract_catalogue.tradeable_terms([term]) == ()
    parsed = contract_catalogue.parse_term(term)
    assert TradingRule.below_floor(*parsed) is True


@pytest.mark.parametrize("term", ["60s", "90s", "120s", "300s", "15m", "1h", "1d"])
def test_terms_at_or_above_the_floor_survive(term):
    assert contract_catalogue.tradeable_terms([term]) == (term,)
    parsed = contract_catalogue.parse_term(term)
    assert TradingRule.below_floor(*parsed) is False


def test_the_exposed_catalogue_drops_sub_minute_terms_and_ticks():
    catalogue = {
        "available": True,
        "contracts": {
            "CALL": {"terms": ["1t", "5t", "15s", "30s", "60s", "5m"]},
            "PUT": {"terms": ["5t"]},
        },
    }
    exposed = contract_catalogue.tradeable_catalogue(catalogue)

    assert exposed["contracts"]["CALL"]["terms"] == ["60s", "5m"]
    assert exposed["contracts"]["PUT"]["terms"] == []
    assert exposed["min_duration_seconds"] == TradingRule.MIN_DURATION_SECONDS
    # The raw catalogue is a venue description and is left untouched.
    assert catalogue["contracts"]["CALL"]["terms"][0] == "1t"


@pytest.mark.parametrize("duration", [1, 5, 15, 30, 45, 59])
def test_paper_book_refuses_a_sub_minute_duration(duration):
    from app.core.errors import AppError

    with pytest.raises(AppError) as excinfo:
        binary.validate_duration(duration)
    assert excinfo.value.detail["code"] == "duration_too_short"


def test_paper_book_accepts_one_minute():
    assert binary.validate_duration(TradingRule.MIN_DURATION_SECONDS) == 60
