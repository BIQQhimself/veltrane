from __future__ import annotations

import ast
import pathlib
from datetime import UTC, datetime

from app.risk.engine import engine
from app.risk.types import (
    DEFAULT_RISK_RULES,
    InstrumentView,
    MarketView,
    OrderIntent,
    PositionView,
    RiskContext,
)

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def intent(**overrides) -> OrderIntent:
    payload = dict(
        org_id="org-1",
        mode="paper",
        symbol="BTC/USDT",
        side="buy",
        quantity=0.01,
        order_type="market",
        client_order_id="co-1",
        idempotency_key="idem-1",
        strategy_status="approved",
        reason="unit test",
    )
    payload.update(overrides)
    return OrderIntent(**payload)


def context(**overrides) -> RiskContext:
    payload = dict(
        now=NOW,
        mode="paper",
        policy=dict(DEFAULT_RISK_RULES),
        equity=25_000.0,
        cash=25_000.0,
        peak_equity=25_000.0,
        instrument=InstrumentView(
            symbol="BTC/USDT", asset_class="crypto", min_qty=0.0001, qty_step=0.0001, max_leverage=3
        ),
        market=MarketView(price=60_000.0, bid=59_990.0, ask=60_010.0, age_seconds=1.0, spread_bps=3.0, source="demo"),
        market_open=True,
        daily_execution_limit=5,
        executions_today=0,
    )
    payload.update(overrides)
    return RiskContext(**payload)


def codes(assessment) -> list[str]:
    return assessment.failed_codes


def test_paper_order_approved():
    assessment = engine.evaluate(intent(), context())
    assert assessment.approved, assessment.failed_codes
    assert assessment.notional == 600.0
    assert all(c.passed for c in assessment.checks)


def test_all_four_kill_switches_block():
    for flag in ("kill_global", "kill_org", "kill_provider", "kill_user"):
        assessment = engine.evaluate(intent(), context(**{flag: True}))
        assert not assessment.approved
        assert "kill_switch" in codes(assessment)


def test_live_requires_every_gate():
    base = dict(
        mode="live",
        global_live_enabled=True,
        org_live_authorized=True,
        org_live_entitlement=True,
        connection_trade_permission=True,
        connection_read_only=False,
    )
    live_intent = intent(mode="live", strategy_status="live", stop_loss=57_000.0)
    assert engine.evaluate(live_intent, context(**base)).approved

    for missing in (
        "global_live_enabled",
        "org_live_authorized",
        "org_live_entitlement",
        "connection_trade_permission",
    ):
        ctx = context(**{**base, missing: False})
        assessment = engine.evaluate(live_intent, ctx)
        assert not assessment.approved, missing
        assert "mode_authorization" in codes(assessment)

    read_only = engine.evaluate(live_intent, context(**{**base, "connection_read_only": True}))
    assert not read_only.approved
    assert "connection_permission" in codes(read_only)


def test_live_strategy_must_be_promoted():
    ctx = context(
        mode="live",
        global_live_enabled=True,
        org_live_authorized=True,
        org_live_entitlement=True,
        connection_trade_permission=True,
        connection_read_only=False,
    )
    assessment = engine.evaluate(intent(mode="live", strategy_status="approved", stop_loss=57_000.0), ctx)
    assert not assessment.approved
    assert "strategy_approved" in codes(assessment)


def test_position_size_and_absolute_cap():
    assessment = engine.evaluate(intent(quantity=0.1), context())  # 6,000 > 10% of 25k
    assert not assessment.approved
    assert "position_size" in codes(assessment)

    tiny = engine.evaluate(intent(quantity=0.00001), context())  # below min_notional
    assert not tiny.approved
    assert "position_size" in codes(tiny)


def test_exposure_and_leverage_caps():
    ctx = context(account_exposure=7_400.0, portfolio_exposure=7_400.0)  # +600 = 8000 = 32%
    assessment = engine.evaluate(intent(quantity=0.01), ctx)
    assert not assessment.approved
    assert "exposure" in codes(assessment)


def test_open_position_cap():
    positions = [PositionView(symbol=f"X{i}/USDT", side="long", quantity=1, notional=100) for i in range(5)]
    assessment = engine.evaluate(intent(), context(positions=positions, open_position_count=5))
    assert not assessment.approved
    assert "max_open_positions" in codes(assessment)


def test_daily_loss_blocks_entries_but_not_exits():
    ctx = context(realized_pnl_today=-800.0, equity=25_000.0)  # >3% of equity
    blocked = engine.evaluate(intent(), ctx)
    assert not blocked.approved
    assert "daily_loss_limit" in codes(blocked)

    exit_order = engine.evaluate(intent(side="sell", reduce_only=True), ctx)
    assert "daily_loss_limit" not in codes(exit_order)


def test_drawdown_circuit_breaker():
    ctx = context(equity=20_000.0, peak_equity=25_000.0)  # 20% drawdown > 15%
    assessment = engine.evaluate(intent(quantity=0.001), ctx)
    assert not assessment.approved
    assert "drawdown_limit" in codes(assessment)


def test_consecutive_loss_breaker():
    assessment = engine.evaluate(intent(), context(consecutive_losses=4))
    assert not assessment.approved
    assert "circuit_breaker" in codes(assessment)


def test_stale_market_data_rejected():
    assessment = engine.evaluate(
        intent(), context(market=MarketView(price=60_000.0, age_seconds=120.0, spread_bps=3.0))
    )
    assert not assessment.approved
    assert "market_data" in codes(assessment)


def test_wide_spread_rejected():
    assessment = engine.evaluate(
        intent(), context(market=MarketView(price=60_000.0, age_seconds=1.0, spread_bps=500.0))
    )
    assert not assessment.approved
    assert "market_data" in codes(assessment)


def test_duplicate_order_rejected():
    assessment = engine.evaluate(intent(), context(duplicate_exists=True))
    assert not assessment.approved
    assert "duplicate_order" in codes(assessment)


def test_demo_execution_limit():
    assessment = engine.evaluate(intent(), context(executions_today=5, daily_execution_limit=5))
    assert not assessment.approved
    assert "demo_execution_limit" in codes(assessment)


def test_live_execution_limit_uses_the_plan_allowance():
    """A plan's daily allowance must bound real money too, not only simulated contracts."""
    live_ctx = context(
        mode="live",
        global_live_enabled=True,
        org_live_authorized=True,
        org_live_entitlement=True,
        connection_trade_permission=True,
        connection_read_only=False,
        live_executions_today=600,
        daily_execution_limit=600,
    )
    blocked = engine.evaluate(intent(mode="live", strategy_status="live", stop_loss=59_000.0), live_ctx)
    assert "live_execution_limit" in codes(blocked)
    assert not blocked.approved

    under = engine.evaluate(
        intent(mode="live", strategy_status="live", stop_loss=59_000.0),
        live_ctx.with_extra(live_executions_today=599),
    )
    assert "live_execution_limit" not in codes(under)


def test_an_uncapped_plan_has_no_live_cap():
    live_ctx = context(
        mode="live",
        global_live_enabled=True,
        org_live_authorized=True,
        org_live_entitlement=True,
        connection_trade_permission=True,
        connection_read_only=False,
        live_executions_today=50_000,
        daily_execution_limit=None,
    )
    assessment = engine.evaluate(intent(mode="live", strategy_status="live", stop_loss=59_000.0), live_ctx)
    assert "live_execution_limit" not in codes(assessment)


def test_stop_loss_validation_for_live():
    live_ctx = context(
        mode="live",
        global_live_enabled=True,
        org_live_authorized=True,
        org_live_entitlement=True,
        connection_trade_permission=True,
        connection_read_only=False,
    )
    missing = engine.evaluate(intent(mode="live", strategy_status="live"), live_ctx)
    assert "stop_loss" in codes(missing)

    wrong_side = engine.evaluate(intent(mode="live", strategy_status="live", stop_loss=61_000.0), live_ctx)
    assert "stop_loss" in codes(wrong_side)

    too_wide = engine.evaluate(intent(mode="live", strategy_status="live", stop_loss=45_000.0), live_ctx)
    assert "stop_loss" in codes(too_wide)

    valid = engine.evaluate(intent(mode="live", strategy_status="live", stop_loss=57_000.0), live_ctx)
    assert valid.approved, valid.failed_codes


def test_instrument_validation():
    too_small = engine.evaluate(intent(quantity=0.000001), context())
    assert not too_small.approved
    assert "instrument_tradable" in codes(too_small)

    bad_step = engine.evaluate(intent(quantity=0.00105), context())
    assert not bad_step.approved
    assert "instrument_tradable" in codes(bad_step)


def test_limit_price_band():
    far = engine.evaluate(intent(order_type="limit", price=90_000.0, quantity=0.01), context())
    assert not far.approved
    assert "order_validation" in codes(far)


def test_market_closed():
    assessment = engine.evaluate(intent(symbol="EUR/USD"), context(market_open=False))
    assert not assessment.approved
    assert "trading_session" in codes(assessment)


def test_zero_equity_rejected():
    assessment = engine.evaluate(intent(), context(equity=0.0, cash=0.0))
    assert not assessment.approved


def test_short_selling_policy():
    rules = {**DEFAULT_RISK_RULES, "allow_short": False}
    assessment = engine.evaluate(intent(side="sell"), context(policy=rules))
    assert not assessment.approved
    assert "order_validation" in codes(assessment)


def test_suspended_account():
    assessment = engine.evaluate(intent(), context(org_suspended=True))
    assert not assessment.approved
    assert "org_suspended" in codes(assessment)


def test_all_failures_reported_not_just_first():
    ctx = context(
        kill_org=True,
        equity=0.0,
        duplicate_exists=True,
        executions_today=99,
        daily_execution_limit=5,
    )
    assessment = engine.evaluate(intent(), ctx)
    failed = codes(assessment)
    assert len(failed) >= 4
    assert {"kill_switch", "duplicate_order", "demo_execution_limit"}.issubset(set(failed))


def test_evaluation_is_deterministic():
    first = engine.evaluate(intent(), context()).as_dict()
    second = engine.evaluate(intent(), context()).as_dict()
    assert first == second


def test_risk_engine_does_not_import_strategy_or_execution_modules():
    """Structural guarantee that AI/strategy code cannot be reached from the risk engine."""
    root = pathlib.Path(__file__).resolve().parents[1] / "app" / "risk"
    forbidden = ("app.strategies", "app.trading", "app.providers", "app.api")
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(forbidden), f"{path.name} imports {node.module}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(forbidden), f"{path.name} imports {alias.name}"


def test_notional_at_the_minimum_is_not_rejected_by_float_error():
    """A stake exactly at min_notional arrives as 9.999999999999998 after stake/price*price."""
    price = 1230.60
    quantity = 10.0 / price
    assert quantity * price < 10.0  # the raw product really does fall short
    market = MarketView(price=price, bid=price - 1, ask=price + 1, age_seconds=1.0, spread_bps=3.0, source="demo")
    instrument = InstrumentView(symbol="R_100", asset_class="synthetic", min_qty=0.0, qty_step=0.0, max_leverage=1)
    assessment = engine.evaluate(intent(quantity=quantity), context(market=market, instrument=instrument))
    assert assessment.approved, [f.message for f in assessment.failed]


def test_consecutive_loss_breaker_holds_both_sides_then_lifts():
    """The breaker must not be avoidable by selling, and must not lock the account for ever."""
    from datetime import timedelta

    held = dict(consecutive_losses=4, last_loss_at=NOW - timedelta(minutes=10))
    for side in ("buy", "sell"):
        assessment = engine.evaluate(intent(side=side), context(**held))
        assert not assessment.approved
        assert "circuit_breaker" in codes(assessment)
    reduce_only = engine.evaluate(intent(side="sell", reduce_only=True), context(**held))
    assert reduce_only.approved, [f.message for f in reduce_only.failed]

    cooled = dict(consecutive_losses=4, last_loss_at=NOW - timedelta(minutes=61))
    assessment = engine.evaluate(intent(), context(**cooled))
    assert assessment.approved, [f.message for f in assessment.failed]
    breaker = next(check for check in assessment.checks if check.code == "circuit_breaker")
    assert breaker.passed and "cooled down" in breaker.message


def test_consecutive_loss_breaker_without_a_timestamp_stays_engaged():
    assessment = engine.evaluate(intent(), context(consecutive_losses=5, last_loss_at=None))
    assert not assessment.approved
    assert "circuit_breaker" in codes(assessment)
