# Trading risk policy

This is the policy the software enforces. It is deliberately conservative and it is enforced by
an engine that the strategy layer cannot influence.

## 1. Separation of concerns

```
Strategy (AI or deterministic)  ──▶  OrderRequest  ──▶  RiskEngine  ──▶  Execution
                                                            │
                                                            └── reject (persisted + audited)
```

- Strategies produce intent. They have no database write access to orders and cannot alter a
  policy.
- The risk engine (`app/risk/engine.py`) is pure and deterministic: given the same inputs it
  returns the same decision. It never calls a model.
- Execution is the only component that talks to a venue, and it re-checks the platform flag and
  the kill switches immediately before doing so.

## 2. Checks

Defaults live in `app/risk/types.py` (`DEFAULT_RISK_RULES`). An owner can change them in the
admin console; every change creates a new `RiskPolicy` version, and orders record the policy
version that evaluated them. Rule codes below are the ones emitted by `app/risk/rules.py`.

| Code | Rule | Default |
| --- | --- | --- |
| `kill_switch` | Global / org / provider / user switch engaged | engaged = reject |
| `mode_authorization` | Live mode requested without entitlement or platform flag | off = reject live |
| `org_suspended` | Tenant suspended by an operator | on |
| `circuit_breaker` | Four consecutive losses hold *new* entries, on either side, for a cool-down (`circuit_breaker_cooldown_minutes`); exits and reduce-only orders stay allowed | 4 losses, 60 min |
| `trading_session` | Instrument inside its trading session | on |
| `instrument_tradable` | Instrument supported by the provider and not halted | on |
| `market_data` | Quote exists and is fresher than the window | 30 s |
| `order_validation` | Quantity, price band, min notional, limit price sanity | min 10 notional, 5 % band |
| `position_size` | Resulting position notional vs equity | 10 % of equity |
| `exposure` | Account and portfolio exposure, leverage | 30 % / 50 % / 3× |
| `max_open_positions` | Count of open positions | 5 |
| `stop_loss` | Live entries must carry a stop inside the allowed band | required, ≤ 12 % |
| `duplicate_order` | An identical contract inside the window: same instrument, side, contract type, stake and duration | 60 s |
| `daily_loss_limit` | Loss for the UTC day | 3 % of equity |
| `drawdown_limit` | Peak-to-trough on the account | 15 % |
| `strategy_approved` | Strategy version approved for the mode in use | on |
| `connection_permission` | Connection allows trading for this mode | on |
| `daily_execution_allowance` | Every execution — paper fill, venue demo contract and real-money contract — against one per-account daily counter | plan allowance (entitlement); Free = 0 |
| `binary_terms` | Fixed-odds expiry must be a term the venue published *and* priced; stake and payout inside the offered bounds | venue menu, verified per term |

Three details are easy to get wrong and are pinned by tests:

- **Durations come from the venue, not from a constant.** `GET /deriv/contracts` reads Deriv's
  `contracts_for`, walks the duration ladder inside each published band and keeps only the terms
  the proposal engine actually prices. The menu therefore contains real Deriv terms — 15 s, 30 s
  and 5 ticks are all normal — and never a duration invented to fill a gap. A term outside the
  menu is rejected with `unsupported_duration` before any order leaves the process, and the
  terminal can only render what the catalogue returned.
- **One minute is the platform floor, on every path.** Deriv prices 15-second and tick contracts;
  VELTRANE does not offer them. The floor is a product decision, not a venue capability, so it is
  enforced once in `TradingRule` (`app/db/constants.py`) and applied at four points: the catalogue
  endpoint drops sub-minute terms before they reach a client, the Deriv preview and contract
  request schemas reject them, the execution layer re-checks the term immediately before the
  proposal call, and the automation runner halts a stored config whose duration is below the
  floor. `tests/test_duration_floor.py` pins each of those points, so a future change to the
  catalogue or a request model cannot quietly reopen a sub-minute path.
- **A tick term never gains a seconds figure.** `duration_seconds` is `None` for `1t`-style
  contracts. Converting ticks to seconds would be a fabricated number, and settlement, the audit
  trail and the duplicate-order window all key off the term instead.

- **Notional is rounded before it is compared.** A stake of exactly the minimum arrives as
  `9.999999999999998` after `stake / price * price`, so it would otherwise fail the minimum-notional
  rule on a binary-search edge of floating point.
- **A fixed-odds position carries its stake as its size.** Exposure is `quantity * mark_price`; for a
  binary, `quantity` is `stake / price`, so the reported exposure equals the money at risk, not the
  price of the underlying.

Rejections are not silent: the order is stored with `status=rejected`, `rejection_reason` holds
the human-readable summary, `risk_decisions.checks` holds every check with pass/fail and detail,
and an `order.rejected` audit row is written. A notification is created for the trader.

## 3. Costs

Nothing is evaluated on gross profit.

- Paper fills apply taker fee (`VELTRANE_PAPER_TAKER_FEE_BPS`, default 10 bps), half-spread
  (`PAPER_SPREAD_BPS`, 4 bps) and slippage (`PAPER_SLIPPAGE_BPS`, 3 bps) against the trade
  direction. Both the estimate and the realised figure are stored per trade.
- Backtests subtract the same fee, spread and slippage per side, plus an optional funding
  accrual for perpetual instruments.
- Portfolio performance is reported net of recorded fees and funding, never gross.
- Funding and borrow costs are modelled as a per-trade field, not assumed to be zero.

## 4. Daily trade allowance

There is **one** allowance per account per UTC day, not one for simulation and one for real money.
A paper fill, a contract on a venue demo account and a real-money contract all increment
`executions_today`, and the risk engine compares it with `daily_execution_cap` before any venue
call (`check_daily_execution_allowance`). The refusal is recorded like any other rejection, with
the plan and the cap in the message. Switching between simulation and live therefore buys no extra
capacity, and the number a customer sees on the dashboard is the number the engine enforces.

Free is capped at **0**: a free account can connect, sync, analyse and read, and every execution
path is refused. That is a risk-engine rejection, not a hidden button — the terminal journey in
`frontend/e2e/journeys.mjs` asserts that no contract is created. VIP carries `-1`, meaning no
VELTRANE-imposed ceiling; the deterministic rules in section 2 and the venue's own limits still
apply.

## 5. Limits and kill switches

Scopes: `global` (platform), `org` (tenant), `provider` (e.g. all Binance trading), `user`
(individual). Engaging a switch:

1. Writes a `KillSwitch` row with actor, reason and timestamp.
2. Mirrors the global state to Redis so workers see it without a database round trip.
3. Optionally flattens open paper positions (`flatten=true`) through the normal order path, so
   even the emergency path is risk-checked and audited.
4. Blocks every subsequent order at the matching scope.

Release requires the same role as engage (owner for global) and is audited.

## 6. Live trading authorisation

Live execution requires all of the following, in order:

1. A plan with `live_trading: true` (Pro and Elite by default; configurable).
2. A connected account with a **verified** read-only synchronisation.
3. A recorded risk acknowledgement of the current risk document version.
4. All eight checklist items accepted.
5. MFA verified within the session, or an explicit written waiver recorded for accounts that
   cannot use TOTP.
6. A confirmation token issued at step 4 and used within 60 seconds (cooling-off).
7. `VELTRANE_LIVE_TRADING_ENABLED=true` at the process level.

Revoking authorisation is immediate and requires no confirmation. Authorisation expires and must
be renewed; the expiry is stored on `trading_permissions`.

## 7. What the platform will not do

- It will not claim, imply or display a guaranteed return.
- It will not optimise for trade frequency.
- It will not present simulated results as real results. Demo payloads carry `is_demo: true` and
  the UI must label them.
- It will not submit an order that failed a risk check, for any reason, including operator
  override. There is no override path in the code.
- It will not enable live trading as part of a subscription purchase or an onboarding step.

## 8. Operator responsibilities

- Review the risk policy before enabling live trading for any tenant.
- Keep `VELTRANE_LIVE_TRADING_ENABLED=false` until the live adapters have been verified against
  real accounts (see INTEGRATIONS.md).
- Monitor `order.rejected` audit volume; a spike usually means a strategy is fighting the limits.
- Keep the kill switch reachable: the admin console, the API, and the file flag are three
  independent paths.
