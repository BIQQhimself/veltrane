"""The duration whitelist is enforced by the risk engine, not by the interface.

These are rule-level tests: no database, no network, no provider. They pin the behaviour
that matters most about contract terms — a duration the venue has not been shown to accept
is refused, and a venue term is never converted into a seconds figure that does not exist.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.risk.rules import check_binary_terms
from app.risk.types import OrderIntent


def _intent(stake: float = 10.0, price: float = 2.0) -> OrderIntent:
    return OrderIntent(
        org_id="org",
        mode="live",
        symbol="R_100",
        side="buy",
        quantity=stake / price,
        order_type="market",
        price=price,
        client_order_id="c1",
        idempotency_key="k1",
    )


def _ctx(price: float = 2.0) -> SimpleNamespace:
    return SimpleNamespace(market=SimpleNamespace(price=price))


def test_venue_term_inside_the_published_menu_passes():
    rules = {
        "binary_terms": {
            "term": "30s",
            "allowed_terms": ["15s", "30s", "5t"],
            "duration_seconds": 30,
            "payout_pct": 95.0,
            "min_stake": 0.35,
            "max_stake": 1000.0,
            "term_source": "venue",
        }
    }
    result = check_binary_terms(_intent(), _ctx(), rules)
    assert result.passed is True
    assert result.detail["term"] == "30s"
    assert result.detail["term_source"] == "venue"


def test_venue_term_outside_the_published_menu_is_rejected():
    rules = {
        "binary_terms": {
            "term": "37s",
            "allowed_terms": ["15s", "30s", "45s"],
            "duration_seconds": 37,
            "payout_pct": 95.0,
            "min_stake": 0.0,
            "max_stake": 1000.0,
            "term_source": "venue",
        }
    }
    result = check_binary_terms(_intent(), _ctx(), rules)
    assert result.passed is False
    assert "37s" in result.message
    assert result.detail["allowed_terms"] == ["15s", "30s", "45s"]


def test_tick_contract_is_accepted_without_a_seconds_equivalent():
    rules = {
        "binary_terms": {
            "term": "5t",
            "allowed_terms": ["1t", "5t", "10t"],
            "duration_seconds": None,
            "payout_pct": 90.0,
            "min_stake": 0.0,
            "max_stake": 1000.0,
        }
    }
    assert check_binary_terms(_intent(), _ctx(), rules).passed is True


def test_unknown_terms_fail_closed():
    rules = {"binary_terms": {"allowed_terms": [], "allowed_durations": [], "payout_pct": 90.0}}
    result = check_binary_terms(_intent(), _ctx(), rules)
    assert result.passed is False


def test_platform_book_still_validates_its_own_seconds_list():
    base = {
        "payout_pct": 80.0,
        "min_stake": 0.0,
        "max_stake": 1000.0,
        "allowed_durations": [60, 300],
        "duration": 60,
        "duration_unit": "s",
        "allowed_terms": ["60s", "300s"],
        "duration_seconds": 60,
    }
    assert check_binary_terms(_intent(), _ctx(), {"binary_terms": dict(base)}).passed is True

    off_menu = {**base, "duration": 90, "term": "90s", "duration_seconds": 90}
    result = check_binary_terms(_intent(), _ctx(), {"binary_terms": off_menu})
    assert result.passed is False


def test_payout_and_stake_bounds_still_apply():
    terms = {
        "term": "30s",
        "allowed_terms": ["30s"],
        "duration_seconds": 30,
        "payout_pct": 99.0,
        "min_stake": 0.0,
        "max_stake": 1000.0,
    }
    assert check_binary_terms(_intent(), _ctx(), {"binary_terms": terms}).passed is False

    low_stake = {**terms, "payout_pct": 90.0, "min_stake": 50.0}
    assert check_binary_terms(_intent(stake=10.0), _ctx(), {"binary_terms": low_stake}).passed is False
