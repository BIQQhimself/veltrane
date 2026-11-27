"""Deterministic risk rules.

Every rule is a pure function of (intent, context, rules). No I/O, no randomness,
no AI input. Rules are evaluated in order and all failures are reported.
"""

from __future__ import annotations

from datetime import timedelta

from app.risk.types import OrderIntent, RiskContext, RuleResult


def _r(code: str, passed: bool, message: str, detail: dict | None = None, severity: str = "blocking") -> RuleResult:
    return RuleResult(code=code, passed=passed, message=message, detail=detail or {}, severity=severity)


def check_kill_switches(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    engaged = [
        name
        for name, value in (
            ("global", ctx.kill_global),
            ("organization", ctx.kill_org),
            ("provider", ctx.kill_provider),
            ("account", ctx.kill_user),
        )
        if value
    ]
    if engaged:
        return _r(
            "kill_switch",
            False,
            f"Trading is halted by an engaged kill switch ({', '.join(engaged)}).",
            {"engaged": engaged},
        )
    return _r("kill_switch", True, "No kill switch is engaged.", {"engaged": []})


def check_org_status(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    if ctx.org_suspended:
        return _r("org_suspended", False, "This account is suspended. Contact support.")
    return _r("org_suspended", True, "Account is in good standing.")


def check_mode_authorization(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    if intent.mode == "paper":
        return _r("mode_authorization", True, "Paper trading is always permitted.", {"mode": "paper"})
    if ctx.venue_demo:
        if not ctx.connection_trade_permission or ctx.connection_read_only:
            return _r(
                "mode_authorization",
                False,
                "This connection is read-only; enable trading on it before routing contracts.",
                {"mode": "live", "venue_demo": True},
            )
        return _r(
            "mode_authorization",
            True,
            "Venue demo account: execution permitted without live authorisation (no real funds).",
            {"mode": "live", "venue_demo": True},
        )
    missing = []
    if not ctx.global_live_enabled:
        missing.append("platform_live_trading_flag")
    if not ctx.org_live_entitlement:
        missing.append("plan_entitlement")
    if not ctx.org_live_authorized:
        missing.append("explicit_user_authorization")
    if not ctx.connection_trade_permission:
        missing.append("connection_trade_permission")
    if ctx.connection_read_only:
        missing.append("connection_not_read_only")
    if missing:
        return _r(
            "mode_authorization",
            False,
            "Live execution is not authorised: " + ", ".join(missing) + ".",
            {"missing": missing},
        )
    return _r("mode_authorization", True, "Live execution fully authorised.", {"mode": "live"})


def check_connection(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    if intent.mode == "paper":
        return _r("connection_permission", True, "Paper session does not require provider permissions.")
    if ctx.connection_read_only or not ctx.connection_trade_permission:
        return _r("connection_permission", False, "The connected account is read-only or lacks trade permission.")
    return _r("connection_permission", True, "Connection has trade permission and no withdrawal scope.")


def check_strategy_status(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    if intent.mode == "paper":
        if intent.strategy_status not in (None, "approved", "live"):
            return _r(
                "strategy_approved",
                False,
                "The strategy version is not approved for execution.",
                {"strategy_status": intent.strategy_status},
            )
        return _r("strategy_approved", True, "Strategy version is approved for paper execution.")
    if intent.strategy_status != "live":
        return _r(
            "strategy_approved",
            False,
            "Live orders require a strategy version explicitly promoted to live.",
            {"strategy_status": intent.strategy_status},
        )
    return _r("strategy_approved", True, "Strategy version is live.")


def check_instrument(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    inst = ctx.instrument
    if not inst.is_active:
        return _r("instrument_tradable", False, f"{inst.symbol} is not tradable.")
    if intent.quantity <= 0:
        return _r("instrument_tradable", False, "Quantity must be greater than zero.")
    if inst.min_qty and intent.quantity < inst.min_qty:
        return _r(
            "instrument_tradable",
            False,
            f"Quantity {intent.quantity} is below the venue minimum of {inst.min_qty}.",
            {"min_qty": inst.min_qty},
        )
    if inst.qty_step:
        steps = round(intent.quantity / inst.qty_step, 6)
        if abs(steps - round(steps)) > 1e-6:
            return _r(
                "instrument_tradable",
                False,
                f"Quantity must be a multiple of {inst.qty_step}.",
                {"qty_step": inst.qty_step},
            )
    return _r("instrument_tradable", True, "Instrument and quantity are valid.")


def check_market_data(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    market = ctx.market
    if market.price is None or market.price <= 0:
        return _r("market_data", False, "No usable reference price is available.")
    max_age = float(rules["max_price_age_seconds"])
    if market.age_seconds is not None and market.age_seconds > max_age:
        return _r(
            "market_data",
            False,
            f"Market data is stale ({market.age_seconds:.0f}s old, limit {max_age:.0f}s).",
            {"age_seconds": market.age_seconds, "max_age_seconds": max_age},
        )
    if market.spread_bps is not None and market.spread_bps > float(rules["max_spread_bps"]):
        return _r(
            "market_data",
            False,
            f"Spread {market.spread_bps:.1f} bps exceeds the {rules['max_spread_bps']} bps limit.",
            {"spread_bps": market.spread_bps},
        )
    return _r("market_data", True, "Market data is fresh and spread is acceptable.")


def check_order_validation(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    if intent.order_type not in ("market", "limit", "stop", "stop_limit"):
        return _r("order_validation", False, f"Unsupported order type '{intent.order_type}'.")
    if intent.side not in ("buy", "sell"):
        return _r("order_validation", False, "Order side must be buy or sell.")
    if intent.side == "sell" and not rules.get("allow_short", True):
        has_long = any(p.symbol == intent.symbol and p.side == "long" for p in ctx.positions)
        if not has_long:
            return _r("order_validation", False, "Short selling is disabled by policy.")
    if intent.order_type in ("limit", "stop_limit"):
        if not intent.price or intent.price <= 0:
            return _r("order_validation", False, "Limit orders require a positive price.")
        band = float(rules["limit_price_band_pct"]) / 100.0
        ref = ctx.market.price
        if ref > 0 and abs(intent.price - ref) / ref > band:
            return _r(
                "order_validation",
                False,
                f"Limit price is more than {rules['limit_price_band_pct']}% away from the market price.",
                {"price": intent.price, "reference": ref},
            )
    if intent.order_type in ("stop", "stop_limit") and (not intent.stop_price or intent.stop_price <= 0):
        return _r("order_validation", False, "Stop orders require a positive trigger price.")
    return _r("order_validation", True, "Order shape is valid.")


def check_duplicate(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    if ctx.duplicate_exists:
        return _r("duplicate_order", False, "An identical order is already pending or was just submitted.")
    return _r("duplicate_order", True, "No duplicate order detected.")


def _notional(intent: OrderIntent, ctx: RiskContext) -> float:
    """Trade notional, rounded to cents-scale precision.

    ``quantity * price`` where the quantity was itself derived as ``stake / price`` loses the last
    bits to binary floating point: a $10 stake comes back as 9.999999999999998 and would trip the
    minimum-notional rule. Rounding to 6 decimals keeps the comparison honest.
    """
    return round(intent.quantity * ctx.market.price, 6)


def check_position_size(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    notional = _notional(intent, ctx)
    min_notional = float(rules["min_notional"])
    if notional < min_notional:
        return _r(
            "position_size",
            False,
            f"Order notional {notional:.2f} is below the {min_notional:.2f} minimum.",
            {"notional": notional, "min_notional": min_notional},
        )
    max_abs = float(rules["max_order_notional_abs"])
    if notional > max_abs:
        return _r(
            "position_size",
            False,
            f"Order notional {notional:.2f} exceeds the absolute cap of {max_abs:.2f}.",
            {"notional": notional, "cap": max_abs},
        )
    equity = max(ctx.equity, 0.0)
    if equity <= 0:
        return _r("position_size", False, "Account equity is zero or unavailable.")
    cap = equity * float(rules["max_position_notional_pct"]) / 100.0
    if notional > cap:
        return _r(
            "position_size",
            False,
            f"Order notional {notional:.2f} exceeds {rules['max_position_notional_pct']}% of equity ({cap:.2f}).",
            {"notional": notional, "cap": cap, "equity": equity},
        )
    return _r("position_size", True, f"Order notional {notional:.2f} is within limits.", {"notional": notional})


def check_exposure(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    notional = _notional(intent, ctx)
    equity = max(ctx.equity, 0.0)
    if equity <= 0:
        return _r("exposure", False, "Account equity is zero or unavailable.")
    account_cap = equity * float(rules["max_account_exposure_pct"]) / 100.0
    portfolio_cap = equity * float(rules["max_portfolio_exposure_pct"]) / 100.0
    projected_account = ctx.account_exposure + notional
    projected_portfolio = ctx.portfolio_exposure + notional
    if projected_account > account_cap:
        return _r(
            "exposure",
            False,
            f"Account exposure would reach {projected_account:.2f}, above the {account_cap:.2f} cap.",
            {"projected": projected_account, "cap": account_cap},
        )
    if projected_portfolio > portfolio_cap:
        return _r(
            "exposure",
            False,
            f"Portfolio exposure would reach {projected_portfolio:.2f}, above the {portfolio_cap:.2f} cap.",
            {"projected": projected_portfolio, "cap": portfolio_cap},
        )
    return _r("exposure", True, "Exposure remains within account and portfolio caps.")


def check_leverage(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    notional = _notional(intent, ctx)
    equity = max(ctx.equity, 0.0)
    if equity <= 0:
        return _r("leverage", False, "Account equity is zero or unavailable.")
    implied = (ctx.account_exposure + notional) / equity
    cap = min(float(rules["max_leverage"]), ctx.instrument.max_leverage or float(rules["max_leverage"]))
    if implied > cap:
        return _r(
            "leverage",
            False,
            f"Implied leverage {implied:.2f}x exceeds the {cap:.2f}x cap.",
            {"implied": implied, "cap": cap},
        )
    return _r("leverage", True, f"Implied leverage {implied:.2f}x is acceptable.", {"implied": implied})


def check_open_positions(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    cap = int(rules["max_open_positions"])
    if ctx.open_position_count >= cap:
        return _r(
            "max_open_positions",
            False,
            f"Maximum of {cap} open positions reached.",
            {"open": ctx.open_position_count, "cap": cap},
        )
    return _r("max_open_positions", True, "Open position count is within limits.")


def check_daily_loss(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    if intent.reduce_only or intent.side == "sell":
        return _r("daily_loss_limit", True, "Exit orders are always allowed by the daily loss rule.")
    equity = max(ctx.equity, 0.0)
    if equity <= 0:
        return _r("daily_loss_limit", False, "Account equity is zero or unavailable.")
    loss = -(ctx.realized_pnl_today + min(ctx.unrealized_pnl, 0.0))
    cap = equity * float(rules["daily_loss_limit_pct"]) / 100.0
    if loss >= cap:
        return _r(
            "daily_loss_limit",
            False,
            f"Daily loss {loss:.2f} has reached the {cap:.2f} limit. New entries are blocked until the next session.",
            {"loss": loss, "cap": cap},
        )
    return _r("daily_loss_limit", True, f"Daily loss {loss:.2f} is within the {cap:.2f} limit.", {"loss": loss})


def check_drawdown(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    if intent.reduce_only or intent.side == "sell":
        return _r("drawdown_limit", True, "Exit orders are always allowed by the drawdown rule.")
    peak = max(ctx.peak_equity, 0.0)
    if peak <= 0:
        return _r("drawdown_limit", True, "No equity peak recorded yet.")
    drawdown = (peak - ctx.equity) / peak * 100.0
    cap = float(rules["max_drawdown_pct"])
    if drawdown >= cap:
        return _r(
            "drawdown_limit",
            False,
            f"Drawdown {drawdown:.2f}% has reached the {cap:.2f}% circuit breaker. Trading is paused.",
            {"drawdown_pct": drawdown, "cap": cap},
        )
    return _r(
        "drawdown_limit", True, f"Drawdown {drawdown:.2f}% is within the {cap:.2f}% cap.", {"drawdown_pct": drawdown}
    )


def check_consecutive_losses(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    cap = int(rules["max_consecutive_losses"])
    cooldown = timedelta(minutes=float(rules.get("circuit_breaker_cooldown_minutes") or 0))
    if cap <= 0 or ctx.consecutive_losses < cap or intent.reduce_only:
        return _r("circuit_breaker", True, "Consecutive-loss circuit breaker is not triggered.")

    # A loss streak on its own is not a reason to lock an account out for ever: the breaker holds
    # new entries for a cool-down, then lets the account trade again.
    released_at = ctx.last_loss_at + cooldown if ctx.last_loss_at and cooldown else None
    if released_at is not None and ctx.now >= released_at:
        return _r(
            "circuit_breaker",
            True,
            f"Loss streak of {ctx.consecutive_losses} cooled down at {released_at.isoformat()}.",
            {"consecutive_losses": ctx.consecutive_losses, "cap": cap},
        )
    remaining = f"{max((released_at - ctx.now).total_seconds() // 60, 0):.0f} min" if released_at else "no cool-down configured"
    return _r(
        "circuit_breaker",
        False,
        f"{ctx.consecutive_losses} consecutive losing trades — new entries held for {remaining}.",
        {"consecutive_losses": ctx.consecutive_losses, "cap": cap, "released_at": released_at.isoformat() if released_at else None},
    )


def check_stop_loss(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    required = bool(rules.get("require_stop_loss_live", True))
    if intent.mode == "live" and required and not intent.reduce_only:
        if not intent.stop_loss:
            return _r("stop_loss", False, "Live entries require a stop-loss.")
        ref = ctx.market.price
        if intent.side == "buy" and intent.stop_loss >= ref:
            return _r("stop_loss", False, "Stop-loss for a long entry must sit below the market price.")
        if intent.side == "sell" and intent.stop_loss <= ref:
            return _r("stop_loss", False, "Stop-loss for a short entry must sit above the market price.")
        distance_pct = abs(ref - intent.stop_loss) / ref * 100.0 if ref else 0.0
        max_distance = float(rules["max_stop_distance_pct"])
        if distance_pct > max_distance:
            return _r(
                "stop_loss",
                False,
                f"Stop-loss is {distance_pct:.1f}% away, wider than the {max_distance:.1f}% policy maximum.",
                {"distance_pct": distance_pct, "cap": max_distance},
            )
        return _r("stop_loss", True, f"Stop-loss validated ({distance_pct:.2f}% away).")
    if intent.stop_loss:
        return _r("stop_loss", True, "Optional stop-loss validated.", {"stop_loss": intent.stop_loss})
    return _r("stop_loss", True, "Stop-loss not required in this mode.")


def check_trading_session(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    if not ctx.market_open:
        return _r("trading_session", False, f"The {ctx.instrument.asset_class} market is closed.")
    return _r("trading_session", True, "Market session is open.")


def check_live_execution_limit(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    """The plan's daily allowance also applies to real-money contracts.

    Demo executions are metered separately, so without this rule a paid plan would cap
    simulated trading and leave live trading unbounded — the opposite of the intent.
    """
    if intent.mode != "live" or ctx.venue_demo:
        return _r("live_execution_limit", True, "No live execution cap applies.")
    if ctx.daily_execution_limit is None:
        return _r("live_execution_limit", True, "This plan carries no daily trade cap.")
    if ctx.live_executions_today >= ctx.daily_execution_limit:
        return _r(
            "live_execution_limit",
            False,
            f"Daily trade limit of {ctx.daily_execution_limit} reached. Upgrade for more.",
            {"executions_today": ctx.live_executions_today, "limit": ctx.daily_execution_limit},
        )
    return _r(
        "live_execution_limit",
        True,
        f"{ctx.live_executions_today}/{ctx.daily_execution_limit} live executions used today.",
        {"executions_today": ctx.live_executions_today, "limit": ctx.daily_execution_limit},
    )


def check_demo_execution_limit(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    # A contract on a venue's demo account is simulated money too, so it shares the same cap as
    # paper execution. Only a real-money account escapes it.
    demo_scope = intent.mode == "paper" or ctx.venue_demo
    if not demo_scope or ctx.daily_execution_limit is None:
        return _r("demo_execution_limit", True, "No demo execution cap applies.")
    if ctx.executions_today >= ctx.daily_execution_limit:
        return _r(
            "demo_execution_limit",
            False,
            f"Daily demo execution limit of {ctx.daily_execution_limit} reached. Upgrade for more.",
            {"executions_today": ctx.executions_today, "limit": ctx.daily_execution_limit},
        )
    return _r(
        "demo_execution_limit",
        True,
        f"{ctx.executions_today}/{ctx.daily_execution_limit} demo executions used today.",
        {"executions_today": ctx.executions_today, "limit": ctx.daily_execution_limit},
    )


RULES = (
    check_kill_switches,
    check_org_status,
    check_mode_authorization,
    check_connection,
    check_strategy_status,
    check_instrument,
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
    check_stop_loss,
    check_trading_session,
    check_live_execution_limit,
    check_demo_execution_limit,
)


def check_binary_terms(intent: OrderIntent, ctx: RiskContext, rules: dict) -> RuleResult:
    """Binary-specific contract terms: duration whitelist, payout and stake bounds.

    The duration whitelist is whatever the venue actually offers. A venue contract carries
    its own ``<value><unit>`` term and the accepted list; the platform's paper book carries
    a fixed seconds list. Nothing is rounded to a neighbouring duration.
    """
    terms = rules.get("binary_terms") or {}
    term = str(terms.get("term") or "")
    if not term:
        value = int(terms.get("duration") or 0)
        unit = str(terms.get("duration_unit") or "")
        term = f"{value}{unit}" if value and unit else ""
    allowed_terms = tuple(terms.get("allowed_terms") or ())
    duration = int(terms.get("duration_seconds") or 0)
    allowed = tuple(terms.get("allowed_durations") or ())
    if allowed_terms:
        if term not in allowed_terms:
            return _r(
                "binary_terms",
                False,
                f"Contract duration {term or 'unknown'} is not offered for this asset. "
                f"Choose one of {list(allowed_terms)}.",
                {"term": term, "allowed_terms": list(allowed_terms), "term_source": terms.get("term_source")},
            )
    elif duration not in allowed:
        return _r(
            "binary_terms",
            False,
            f"Contract duration {duration}s is not offered. Choose one of {list(allowed)}.",
            {"duration_seconds": duration, "allowed": list(allowed)},
        )
    payout = float(terms.get("payout_pct") or 0)
    # Implausibility guard, not a venue rule: a fixed-odds payout near or above the stake
    # means the proposal is stale, duplicated or mispriced. The venue's own ceiling sits
    # around 95.6 %, so a tighter bound would refuse legitimate contracts.
    if not 1 <= payout <= 98:
        return _r(
            "binary_terms",
            False,
            f"Payout {payout}% is outside the permitted 1-98% band.",
            {"payout_pct": payout},
        )
    stake = float(intent.quantity) * float(ctx.market.price or 0)
    min_stake = float(terms.get("min_stake") or 0)
    max_stake = float(terms.get("max_stake") or 0)
    if stake < min_stake:
        return _r(
            "binary_terms",
            False,
            f"Stake {stake:.2f} is below the {min_stake:.2f} minimum.",
            {"stake": stake, "min_stake": min_stake},
        )
    if max_stake and stake > max_stake:
        return _r(
            "binary_terms",
            False,
            f"Stake {stake:.2f} exceeds the {max_stake:.2f} per-contract cap.",
            {"stake": stake, "max_stake": max_stake},
        )
    label = term or f"{duration}s"
    return _r(
        "binary_terms",
        True,
        f"{label} contract accepted at {payout:.0f}% payout for a {stake:.2f} stake.",
        {
            "term": term,
            "duration_seconds": terms.get("duration_seconds"),
            "payout_pct": payout,
            "stake": stake,
            "term_source": terms.get("term_source"),
        },
    )
