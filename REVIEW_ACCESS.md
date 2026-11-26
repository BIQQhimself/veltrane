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
| `trader@veltrane.dev` | `Veltrane!Test2026` | Pro | — | A working paper session with closed trades and cost attribution |
| `analyst@veltrane.dev` | `Veltrane!Test2026` | Elite | `analyst` | Read-mostly staff view of the command centre |
| `owner@veltrane.dev` | `Veltrane!Test2026` | Elite | `owner` | Full admin: plans, risk policy, kill switches, refunds, audit log |

Staff accounts are seeded, not self-registered. `analyst` and `owner` differ only in what
the admin API will let them do; both are audited.

To recreate or repair the accounts (idempotent, resets the password hash):

```bash
cd backend
.venv/bin/python -m scripts.seed_testers
VELTRANE_TESTER_PASSWORD='a-stronger-password' .venv/bin/python -m scripts.seed_testers
```

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
5. **Strategies → Paper session.** Start a session on Aurum Trend. It keeps trading on its
   own: a background runner ticks every running session once a minute, whether or not a
   browser is open. Watch equity move, then stop the session.
6. **Analytics.** Attribution by instrument and by strategy version, with every fee shown
   as a deduction. Nothing is annualised or extrapolated.
7. **Kill all trading** (bottom of the sidebar). Engage it, confirm new entries are
   rejected, then release it. The switch lives in the database, so it holds even if the app
   is closed and restarted.
8. **Settings → Live trading.** Try to enable it. The checklist refuses to complete while
   prerequisites are unmet, and the platform flag is off regardless.
9. **Sign in as `owner@veltrane.dev`** and open `/admin`. MRR, ARR, conversion, churn,
   revenue by tier, provider readiness, the paper runner's last tick, feature flags, risk
   policy, audit log. No subscriber credential is ever rendered, in any view.
10. **Try to reach `/admin` as `free@veltrane.dev`.** You get a 404, not a 403: staff
    surfaces are not advertised to non-staff.

## Limits of this build

`KNOWN_LIMITATIONS.md` lists every gap. The ones that matter most for a review:

- No venue integration has been verified against a funded live account. Provider status is
  reported as `implemented unverified` or `scaffold`, never "ready".
- Market data is synthetic. Performance on the demo feed says nothing about real markets.
- No legal, regulatory or tax review has been done. No performance fee is charged.
- The instance is a single-node development deployment: no HA, no load testing, no
  penetration test.
