"""Risk evaluation for fixed-odds binary contracts.

Binaries reuse the same deterministic rule set as spot orders. The mapping is:

* ``quantity = stake / price`` so every existing notional rule (position size,
  exposure, leverage) evaluates the *stake*, which is the true maximum loss of a
  binary contract.
* ``check_stop_loss`` is excluded on purpose: a binary has no stop, the stake is
  capped by the contract terms and the position-size rule. Documented in
  TRADING_RISK_POLICY.md rather than silently skipped.
* ``check_binary_terms`` is binary-specific: duration whitelist, payout bounds and
  stake bounds.

The evaluator is pure, like the spot engine: no DB, no clock, no network.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.risk.rules import (
    check_binary_terms,
    check_consecutive_losses,
    check_daily_loss,
    check_demo_execution_limit,
    check_drawdown,
    check_duplicate,
    check_exposure,
    check_kill_switches,
    check_leverage,
    check_market_data,
    check_mode_authorization,
    check_open_positions,
    check_order_validation,
    check_org_status,
    check_position_size,
    check_trading_session,
)
from app.risk.types import OrderIntent, RiskAssessment, RiskContext, RuleResult, merged_rules


def check_binary_instrument(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    """Binaries stake a notional amount, so quantity step-size does not apply.

    This replaces ``check_instrument`` for fixed-odds contracts and keeps only the
    tradability assertion that still makes sense.
    """
    if not ctx.instrument.is_active:
        return RuleResult(
            code="instrument_tradable",
            passed=False,
            message=f"{intent.symbol} is not currently tradable.",
            detail={"symbol": intent.symbol},
        )
    return RuleResult(
        code="instrument_tradable",
        passed=True,
        message=f"{intent.symbol} is tradable for fixed-odds contracts.",
        detail={"symbol": intent.symbol, "asset_class": ctx.instrument.asset_class},
    )


BINARY_RULES = (
    check_kill_switches,
    check_org_status,
    check_mode_authorization,
    check_binary_instrument,
    check_market_data,
    check_order_validation,
    check_duplicate,
    check_position_size,
    check_exposure,
    check_leverage,
    check_open_positions,
    check_daily_loss,
    check_drawdown,
    check_consecutive_losses,
    check_trading_session,
    check_demo_execution_limit,
    check_binary_terms,
)


@dataclass(frozen=True)
class BinaryTerms:
    duration_seconds: int
    payout_pct: float
    min_stake: float
    max_stake: float
    allowed_durations: tuple[int, ...]

    def as_dict(self) -> dict:
        return {
            "duration_seconds": self.duration_seconds,
            "payout_pct": self.payout_pct,
            "min_stake": self.min_stake,
            "max_stake": self.max_stake,
            "allowed_durations": list(self.allowed_durations),
        }


def evaluate(intent: OrderIntent, ctx: RiskContext, terms: BinaryTerms) -> RiskAssessment:
    rules = merged_rules(ctx.policy)
    checks: list[RuleResult] = [rule(intent, ctx, rules) for rule in BINARY_RULES[:-1]]
    checks.append(check_binary_terms(intent, ctx, {**rules, "binary_terms": terms.as_dict()}))
    approved = all(c.passed for c in checks if c.severity == "blocking")
    return RiskAssessment(
        approved=approved,
        checks=checks,
        policy_id=ctx.policy_id,
        policy_version=ctx.policy_version,
        intent=intent,
        notional=round(intent.quantity * (ctx.market.price or 0.0), 8),
        reference_price=ctx.market.price or 0.0,
    )
