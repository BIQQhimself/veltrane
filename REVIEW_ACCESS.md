# Review access

This instance is a **shared development instance**. It runs with the deterministic demo
market feed, the mock payment provider, and live trading disabled at the platform level.
Nothing here can move real money.

- Web app: <https://work-1-yyquyizfoqebbjmm.prod-runtime.all-hands.dev>
- API health: <https://work-1-yyquyizfoqebbjmm.prod-runtime.all-hands.dev/api/v1/health>
- Admin command centre: `/admin` (staff accounts only)

## Accounts

All seeded accounts use the same password. It exists only on this dev instance and is
regenerated on every seed run (`backend/scripts/seed_testers.py`).

| Email | Password | Plan | Staff role | Use it to check |
| --- | --- | --- | --- | --- |
| `free@veltrane.dev` | `Veltrane!Test2026` | Free | — | Read-only connections, 5 demo executions/day, upgrade prompts, no live execution |
| `basic@veltrane.dev` | `Veltrane!Test2026` | Basic | — | 2 strategies, tighter position and account limits |
| `pro@veltrane.dev` | `Veltrane!Test2026` | Pro | — | Backtests, strategy customisation, 250 demo executions/day, fuller analytics |
| `elite@veltrane.dev` | `Veltrane!Test2026` | Elite | — | Full strategy library, highest limits, performance-fee module |
| `analyst@veltrane.dev` | `Veltrane!Test2026` | Elite | `analyst` | Read-mostly staff view of the command centre |
| `demo@veltrane.ai` | `Veltrane!Demo2026` | Pro | — | A seeded account with a running paper session, 42 settled contracts, an open position and cost attribution |

The staff **owner** is a separate account, created by `backend/scripts/seed.py` from
`VELTRANE_ADMIN_EMAIL` and `VELTRANE_ADMIN_PASSWORD` in `.env`. Ask the operator for those
values; they are not in this file and not in git. Re-running the seed resets that password from
the environment, so a rotated password always matches.

Staff accounts are seeded, not self-registered. `analyst` and `owner` differ in what the admin
API will let them do; both are audited. An owner-only admin action attempted by the analyst
account returns `404`, not `403`: staff surfaces are not advertised to a caller who cannot use
them.

To recreate or repair the accounts (idempotent, resets the password hash):

```bash
cd backend
.venv/bin/python -m scripts.seed            # plans, strategies, flags, staff owner
.venv/bin/python -m scripts.seed_testers    # the tier accounts
.venv/bin/python -m scripts.seed_demo       # the seeded account with history
VELTRANE_TESTER_PASSWORD='a-stronger-password' .venv/bin/python -m scripts.seed_testers
```

Login is rate limited per address. If a script hammers `/auth/login` it will answer `429` for a
while; that is the limiter, not a broken password. Space repeated logins by ~15 s.

## What is real and what is simulated

Read this before drawing conclusions from any number on screen.

| Area | State on this instance |
| --- | --- |
| Authentication, sessions, MFA, audit | Real, enforced server-side |
| Tenancy, entitlements, plan limits | Real, enforced server-side on every call |
| Billing | **Mock provider.** Signature verification, idempotency, renewals and refunds are real code paths; no money moves |
| Market data | **Deterministic demo feed.** Prices are synthetic, seeded and stable per symbol |
| Paper trading | Real engine, real accounting, real risk decisions, simulated fills |
| Live trading | Disabled by platform flag. No adapter can submit an order |
| Exchange connections | Real credential encryption and permission checks; venue calls are not verified against a funded account |
| Email | Written to the outbox, not delivered (no SMTP configured) |
| Performance fees | Implemented and configurable, not enabled; needs legal review |

## Ten-minute tour

1. **Sign in as `pro@veltrane.dev`.** The terminal opens on `BTC/USDT`.
2. **Risk budget strip** above the chart shows how much daily-loss, drawdown, exposure,
   position and demo-execution headroom is left before the risk engine blocks entries. It
   is computed with the same arithmetic the engine uses, and it cannot approve anything.
3. **Toggle VWAP and RSI 14** on the chart toolbar. RSI opens its own pane with 70/30
   guides; the time axis switches to dates on multi-day ranges.
4. **Place a 5-minute call** with a $100 stake. You get a rejection-or-fill decision from
   the risk engine, a settlement countdown, and a full contract record. Then open
   **Settled** and click any contract: entry reason, checks passed and failed, fees,
   slippage estimate against actual, net P&L, and whether a human intervened.
5. **Terminal as `elite@veltrane.dev`.** That account holds a Deriv demo connection with three
   settled contracts seeded through the public API by
   `python -m scripts.seed_deriv_history --email elite@veltrane.dev`. Open a trade: entry reason,
   the contract's stake and payout, the venue's own margin note, risk checks, and the settlement the
   gateway returned. Then place a contract yourself and close it from the open-contracts list. After
   four consecutive losses the breaker holds new entries for an hour and says so; the seeded history
   stops at three so you can still try one.
6. **Strategies → Paper session.** Start a session on Aurum Trend (`pro@veltrane.dev`), or open
   `demo@veltrane.ai`, which already has one running with 42 settled trades. It keeps trading on its
   own: a background runner ticks every running session once a minute, whether or not a
   browser is open. Watch equity move, then stop the session.
7. **Analytics.** Attribution by instrument and by strategy version, with every fee shown
   as a deduction. Nothing is annualised or extrapolated.
8. **Kill all trading** (bottom of the sidebar). Engage it, confirm new entries are
   rejected, then release it. The switch lives in the database, so it holds even if the app
   is closed and restarted.
9. **Settings → Live trading.** Try to enable it. The checklist refuses to complete while
   prerequisites are unmet, and the platform flag is off regardless.
10. **Sign in as the staff owner** (`VELTRANE_ADMIN_EMAIL`) and open `/admin`. MRR, ARR, conversion, churn,
   revenue by tier, provider readiness, the paper runner's last tick, feature flags, risk
   policy, audit log. No subscriber credential is ever rendered, in any view.
11. **Try to reach `/admin` as `free@veltrane.dev`.** You get a 404, not a 403: staff
    surfaces are not advertised to non-staff.

## Verified on this instance

Checked against the running API on 2026-11-26, not inferred from the code. Each line is what the
server answered.

| Check | Observed |
| --- | --- |
| Login for every tier account, the analyst and the staff owner | `200`, subscription active on the expected plan |
| Free account opens a Deriv demo connection | `201`, permissions `read: true, trade: true, withdraw: false` |
| Free account places demo contracts | first five approved, sixth refused with `demo_execution_limit` (and `max_open_positions` once the plan cap is reached) |
| Free account live trading state | `live_enabled: false`; the platform flag and entitlement are both off |
| Identical contract submitted twice | `409 duplicate_order` |
| Same symbol, different stake | second contract accepted and priced on its own |
| Autotrade runner on the demo feed | emits a pending signal when the EMA cross fires, with the trigger reason recorded |
| Signal refused by the risk engine | stored `rejected`, no venue contract id, order row kept for the audit trail |
| Demo account data (`demo@veltrane.ai`, mock venue) | 42 settled contracts, 1 open position, 1 running paper session, costs attributed per trade |
| Deriv demo history (`elite@veltrane.dev`) | 3 settled contracts, each opening a full trade record: reason, stake, payout, settlement payload, net P&L |
| Trade detail for a Deriv contract | `200` with `cost_summary`, `fees_breakdown`, `risk_snapshot.cost_note`, `risk_decision`, exit reason |
| Consecutive-loss breaker | holds entries on both sides, names the remaining cool-down, lets reduce-only exits through |
| Analyst opens the command centre | `200` on overview, revenue, kill-switch state, users and audit |
| Analyst attempts owner-only writes | `404 not_found` on plan edit, kill-switch engage, cost model and email delivery — staff surfaces are not advertised |
| Staff owner | full admin surface: overview, revenue, kill switches, connections, audit log |
| Credentials in admin payloads | none: no key, hint or hash in `/admin/users` |
| Login brute force | `429` after a burst, as designed |

## Limits of this build

`KNOWN_LIMITATIONS.md` lists every gap. The ones that matter most for a review:

- No venue integration has been verified against a funded live account. Provider status is
  reported as `implemented unverified` or `scaffold`, never "ready".
- Market data is synthetic. Performance on the demo feed says nothing about real markets.
- No legal, regulatory or tax review has been done. No performance fee is charged.
- The instance is a single-node development deployment: no HA, no load testing, no
  penetration test.
