# Subscriptions and entitlements

## Tiers

Prices are stored in the `plans` table and editable from the admin console. The figures below are
the seeded defaults.

Four paid tiers plus a free sandbox account. The free account is not a sales tier: it exists so a
visitor can see the platform work without a card, and it never executes a real-money order.

| Tier | Price / month | Connections | Open positions | Trades / day | Agent mode | Backtests / day | Live trading |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Free | $0 | 2 | 3 | 0 (no execution) | off | 0 | no |
| Basic | $19 | 3 | 5 | 600 | while the platform is open | 0 | eligible |
| Pro | $49 | 8 | 15 | 1,200 | background, platform closed | 25 | eligible |
| Elite | $149 | 25 | 50 | 2,400 | background, platform closed | 200 | eligible |
| VIP | $349 | 50 | 100 | no VELTRANE cap | background, platform closed | 500 | eligible |

The VIP price is a **placeholder** for the operator to set. Nothing in the product depends on it;
the plan row is editable from the admin console, and the tier exists so an account can run without
a VELTRANE-imposed daily ceiling. "No VELTRANE cap" is not "no limits": every deterministic risk
rule still applies, and the venue's own API rate limits and contract sizes bound execution.

"Trades / day" is **one** allowance per account covering both environments. A simulated (demo or
paper) execution, an automated signal and a real-money contract all draw on the same counter, so
switching between simulation and live cannot buy a second allowance. The count is
`executions_today` and the ceiling is `daily_execution_cap`, both resolved server-side from the
plan; the risk engine rule `check_daily_execution_allowance` rejects the order at the cap.

Free has a cap of **0**. It is not a small trial allowance: the account can connect, sync and
analyse, and every execution path (terminal, automation, API) returns a rejection that names the
plan. That is enforced by the risk engine, not by a hidden button — see
[TRADING_RISK_POLICY.md](TRADING_RISK_POLICY.md).

A VIP cap of `-1` means "no VELTRANE-imposed ceiling". Every other deterministic rule still
applies: position size, exposure, leverage, daily loss, drawdown, duplicate orders, stale data and
the kill switches.

Changing the catalog in code does not silently rewrite the live database. Startup only creates
plans that are missing (`ensure_plans`), so an administrator's price or limit edit survives a
restart. Pushing catalog changes to existing rows is deliberate:

```bash
cd backend
.venv/bin/python -m app.scripts.sync_plans           # show the diff
.venv/bin/python -m app.scripts.sync_plans --apply   # write it
```

Feature flags per tier (server-side, `app/db/constants.py::Entitlement`):

| Entitlement | Free | Basic | Pro | Elite | VIP |
| --- | --- | --- | --- | --- | --- |
| `strategy_library` | trend only | 2 strategies | 3 strategies | full | full |
| `backtesting` | – | – | ✓ | ✓ | ✓ |
| `strategy_customization` | – | – | ✓ | ✓ | ✓ |
| `advanced_analytics` | – | – | ✓ | ✓ | ✓ |
| `automation` | – | ✓ (session) | ✓ (background) | ✓ (background) | ✓ (background) |
| `portfolio_optimization` | – | – | – | ✓ | ✓ |
| `priority_support` | – | – | – | ✓ | ✓ |
| `api_access` | – | – | ✓ | ✓ | ✓ |
| `performance_fees` | – | – | – | eligible | eligible |
| `live_trading` | – | eligible | eligible | eligible | eligible |

Free is explicitly **read-only**. It is not a trial that can be nudged into execution: the
`live_trading` entitlement is absent, the execution allowance is zero, and both the
live-authorisation endpoint and the risk engine refuse a free account regardless of how the
request is formed.

Basic, Pro, Elite and VIP carry `live_trading: true`, which makes an account *eligible*. It authorises
nothing. Live execution additionally needs the platform live switch, the explicit multi-step
authorisation, a passed safety checklist and a clean risk decision, as described in
[TRADING_RISK_POLICY.md](TRADING_RISK_POLICY.md#6-live-trading-authorisation). The difference
between the tiers is how much the agent may do unattended, not whether a safety control applies.

## Where entitlements are enforced

`app/services/entitlements.py::resolve_entitlements(db, org_id)` merges, in order:

1. Plan limits and features for the org's active subscription.
2. Any `EntitlementOverride` rows granted by staff (with an expiry and a reason).

The result is cached per request, never per client. Every gated endpoint calls
`require_entitlement(...)` or reads a limit from the resolved dict. There is no code path where a
client-supplied plan, limit or feature flag is trusted.

Limits of `0` mean "no numeric cap"; booleans gate a feature outright.

## Subscription lifecycle

```
                 checkout (server-created)
   none ──────────────────────────────▶ incomplete
                                            │ verified webhook: checkout.session.completed
                                            ▼
                                        active ──webhook: invoice.payment_failed──▶ past_due
                                            │                                          │
                     webhook: subscription.deleted │                       retry succeeds │
                                            ▼                                          ▼
                                        canceled ◀────────grace period expires──── active
```

- Only a **signature-verified webhook** moves a subscription into `active`. The mock provider used
  in tests and local development signs the same payload shape as Stripe.
- Webhook events are stored with a unique `(provider, event_id)`; a replay returns
  `{"status": "already_processed"}` and changes nothing.
- `past_due` keeps read access and paper trading for a 7-day grace period, then downgrades to Free
  entitlements. It never keeps live trading enabled.
- Cancellation is immediate for entitlements but keeps the invoice history.
- Refunds are staff-only, capped at the captured amount, and recorded with a reason.
- A failed payment creates an in-app notification and an outbox email.

## Plan changes

`POST /billing/change-plan` supports upgrade and downgrade. Upgrades take effect immediately with
a prorated invoice line; downgrades take effect at the end of the current period. Both paths are
tested (`tests/test_billing.py`).

If a downgrade would leave the account over its new limits (too many open positions or
connections), the API returns `409 downgrade_blocked` listing what must be closed first, rather
than silently violating the limits.

## Performance fees (Elite and VIP only)

Implemented in `app/services/performance_fees.py`, disabled by default.

Rules:

1. Only realised P&L counts. Unrealised gains are never charged.
2. A per-organisation **high-water mark** is maintained. No fee is charged until cumulative
   realised P&L exceeds the previous high-water mark.
3. Losses must be recovered before any further fee accrues.
4. Each calculation stores a snapshot: period, realised P&L, HWM before and after, rate, fee
   amount, trades considered, and the settings in force at the time.
5. A record starts as `draft`, is reviewed, then `invoiced`. Only invoiced records may be billed.
6. Consent is explicit and stored per organisation with the terms version and timestamp.
7. A jurisdiction gate must be satisfied, and `legal_review_required` must be cleared by an owner
   after a real legal review. Until then the module refuses to enable — including in the admin
   API, which returns `400 legal_review_required`.

The module is not revenue-ready. It exists so the accounting is correct when the legal work
completes, and so it cannot be switched on by accident.

## Referral revenue

Referral commission from the Deriv partner programme is tracked separately from subscriptions and
performance fees. The platform records only what it can observe: a click (once per opaque visitor
per 12 hours), a registration attributed to that visitor, an OAuth start, and a connection. It
never guesses commission. An operator copies the verified figure from the Deriv partner statement
into the command centre, and that record — amount, currency, note, actor and timestamp — is the
only thing counted as commission. The funnel shows verified and unverified counts side by side so
nobody mistakes an estimate for revenue.

Referral commission is not netted against performance fees, is not paid out by VELTRANE, and does
not change a subscriber's entitlements.

## Business analytics

`/admin/revenue` and `/admin/costs` compute, from stored rows:

- MRR and ARR (sum of active plan prices, normalised monthly), MRR movement by tier
- New subscriptions, churn count and rate, retention, free-to-paid conversion
- Upgrades and downgrades by tier, revenue by tier
- Payment failures and refunds
- AI cost per subscriber, infrastructure cost per subscriber, support cost per subscriber
- Contribution margin per tier and in aggregate
- Performance-fee revenue, reported separately from subscription revenue

Cost inputs are editable in `/admin/costs` rather than estimated inside the code, so the margin
numbers are only as honest as the operator's inputs. Where a denominator is zero the API returns
`null` instead of a fabricated ratio.
