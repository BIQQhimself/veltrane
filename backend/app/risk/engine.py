"""The independent risk engine.

Guarantees:
* Pure evaluation: no DB session, no network, no clock reads inside rules.
* Every rule runs; all failures are returned, not just the first.
* A rejected assessment is a hard stop for the execution gateway.
"""

from __future__ import annotations

from app.risk.rules import RULES
from app.risk.types import (
    DEFAULT_RISK_RULES,
    OrderIntent,
    RiskAssessment,
    RiskContext,
    RuleResult,
    merged_rules,
)


class RiskEngine:
    version = "1.0.0"

    def evaluate(self, intent: OrderIntent, ctx: RiskContext) -> RiskAssessment:
        rules = merged_rules(ctx.policy or DEFAULT_RISK_RULES)
        checks: list[RuleResult] = []
        for rule in RULES:
            result = rule(intent, ctx, rules)
            checks.append(result)
            if not result.passed and result.severity == "blocking":
                # Keep evaluating: operators need the complete picture in the audit record.
                continue
        approved = all(c.passed for c in checks if c.severity == "blocking")
        reference_price = ctx.market.price or 0.0
        return RiskAssessment(
            approved=approved,
            checks=checks,
            policy_id=ctx.policy_id,
            policy_version=ctx.policy_version,
            intent=intent,
            notional=round(intent.quantity * reference_price, 8),
            reference_price=reference_price,
        )


engine = RiskEngine()
