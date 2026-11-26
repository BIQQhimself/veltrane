# Testing

## Running the backend suite

```bash
cd backend
createdb veltrane_test                      # once
.venv/bin/python -m pytest                  # 233 tests, ~80 s
.venv/bin/python -m pytest -k risk -q       # one slice
.venv/bin/python -m pytest tests/test_trading.py -x --pdb
```

The suite runs against **real PostgreSQL and real Redis** (database `veltrane_test`, Redis db 9).
Nothing is mocked at the database boundary, so SQL, constraints, JSONB behaviour and transaction
semantics are all exercised. Redis is flushed between tests; the schema is recreated once per
session.

Market data comes from the deterministic demo feed (`VELTRANE_MARKET_DATA_SOURCE=demo`), so quotes
are reproducible. Billing uses the signed mock provider, which goes through the same verification
code as Stripe.

## What each file covers

| File | Focus |
| --- | --- |
| `test_auth_and_system.py` | Registration, verification, login, MFA, refresh rotation, logout, password reset |
| `test_billing.py` | Plans, checkout, webhook verification and replay, plan change, cancellation, invoices |
| `test_connections.py` | Provider listing, connection creation, credential encryption, sync, error handling, no secret leakage |
| `test_scheduler.py` | The unattended paper runner: due-session selection, tick effects, error isolation, and that it never touches live state |
| `test_risk_budget.py` | Headroom report matches the blocking rules (daily loss cap arithmetic), reflects kill switches, is read-only, and is tenant-scoped |
| `test_tenancy.py` | Cross-tenant reads and writes return 404 for orders, trades, positions, connections, notifications, backtests, paper sessions |
| `test_strategies_and_entitlements.py` | Strategy catalogue, versioning and approval, backtests, paper sessions, entitlement gating by tier |
| `test_risk_engine.py` | Each rule in isolation, and the composition of rules into a decision |
| `test_trading.py` | Order submission, risk rejection, duplicate prevention, fills, fees, P&L, close, cancel, kill switches, live gating |
| `test_admin.py` | RBAC, overview and revenue, plan editing, risk policy versioning, kill switches, flags, audit, support, costs |
| `test_performance_fees.py` | HWM accounting, loss recovery, legal-review gate, consent, invoicing |
| `test_portfolio_and_notifications.py` | Portfolio overview and performance (equity curve seeded with starting balance, drawdown measured on equity), notification feed, order and trade notifications, support tickets, settings |
| `test_security.py` | Headers, password hashing, login rate limit, token tampering, CSRF, MFA secret at rest, error hygiene, session revocation |
| `test_deriv_integration.py` | Deriv end to end against a protocol-faithful mock gateway: PAT auth, OTP session lifecycle, proposals, contract open/close, execution gate, risk engine, persistence, serialisation |
| `test_deriv_strategy.py` | The baseline autotrade strategy's signal logic on synthetic series: entry timing, RSI filter, and that it stays silent without a confirmed cross |
| `test_deriv_provider.py` | The adapter in isolation: PAT auth, identity, pricing, execution and reconnection against the mock gateway |
| `test_deriv_live_market_data.py` | Public Deriv market data end to end. Skipped unless `VELTRANE_DERIV_LIVE_TESTS=1`, because it needs the real public socket |
| `test_deriv_autotrade.py` | The scheduled runner: deterministic EMA-cross series, approval-mode signals, autonomous execution on a demo account, kill-switch refusal, and a risk rejection that is recorded as rejected rather than executed |
| `test_binary.py` | Fixed-odds contracts: quote, open, settle, payout, expiry, and that a paper binary never touches live equity |
| `test_paper_session.py` | Paper session provisioning, per-session isolation, stop, and balance accounting |
| `test_market_data.py` | The demo feed's shape and continuity, instrument specs, market open/closed behaviour |
| `test_migrations.py` | `alembic upgrade head` produces the same schema the ORM declares |

## Safety invariants asserted by tests

These are not aspirations; each is checked.

1. A Free account cannot place a live order, whatever it sends (`test_trading.py`).
2. Live execution is refused while `VELTRANE_LIVE_TRADING_ENABLED=false`, even for an authorised
   Elite account with a verified connection.
3. The fifth simulated execution succeeds and the sixth is rejected on the Free tier — and a
   contract on a venue *demo* account counts against that same allowance, because it is simulated
   money too (`test_deriv_integration.py`, `test_trading.py`).
4. Every order — accepted or rejected — has a `risk_decisions` row and an audit entry.
5. A repeated idempotency key returns the original order and does not create a second fill.
6. Engaging the kill switch at any scope blocks the next order; releasing it restores trading.
7. An expired or forged webhook signature changes nothing.
8. No API response contains a credential, a key hint for another tenant, or a password hash.
9. Cross-tenant object access returns 404, not 403 and not data.
10. A non-staff account gets 404 on every admin route.
11. Performance fees cannot be enabled without a recorded legal review.
12. Paper trades are marked `is_demo: true` and excluded from live equity.
13. A signal the risk engine refuses is stored as `rejected`, never as `executed`, and no venue
    contract id is attached to it (`test_deriv_autotrade.py`).
14. Duplicate prevention blocks an *identical* submission only: the same underlying with a
    different stake, contract type or duration is a new order and is priced on its own merits
    (`test_deriv_integration.py`).
15. A fixed-odds position reports its stake as exposure, not the underlying price, so a handful of
    small contracts cannot exhaust the account exposure limit (`test_deriv_integration.py`).

## Linting and static checks

Backend lint uses Ruff, configured in `backend/pyproject.toml` (Python 3.13 target, 120 columns,
rules `E4`/`E7`/`E9`/`F`/`I`/`UP`/`B`). The rule set is deliberately narrow: correctness, import
order and modernisation, not restyling. `B008` is resolved through
`flake8-bugbear.extend-immutable-calls` because FastAPI dependency injection is a call in a default
argument, and `E402` is ignored only in `tests/conftest.py` and `alembic/env.py`, which must set up
the environment before importing the app.

```bash
cd backend
.venv/bin/pip install ruff==0.17.6
.venv/bin/ruff check app tests
.venv/bin/ruff check app tests --fix    # safe fixes only
```

Frontend lint uses ESLint 9 with a flat config (`frontend/eslint.config.mjs`) that extends
`next/core-web-vitals` and `next/typescript` through `FlatCompat`. `next lint` is deprecated in
Next.js 15.5, so the `lint` script calls `eslint .` directly.

```bash
cd frontend
npm run lint        # eslint .
npm run typecheck   # tsc --noEmit
npm run build       # production build
```

Dependency audit runs `pip-audit -r requirements.txt --strict` in CI. Ruff and pip-audit are pinned
in the workflow so lint results do not drift between runs.

## Frontend tests

The front end is checked with TypeScript (`npm run typecheck`), ESLint (`npm run lint`), a
production build (`npm run build`) and Vitest (`npm run test`). `vitest.config.ts` resolves the `@/`
alias and runs in a node environment, so tests cover pure logic rather than DOM. The chart suite
(`src/components/charts/candles.test.ts`, 16 tests) pins the price scale that keeps a stale or
cross-instrument quote from flattening a chart, the time-axis tick spacing including the switch from
clock times to dates on multi-day ranges, and the VWAP and Wilder RSI helpers (flat windows are
neutral at 50, values stay inside 0–100, and the series aligns to the candle index).
`src/lib/risk-budget.test.ts` (5 tests) pins the wording and tone of the risk-posture badge so the
overview can never say "within limits" while a budget is breached. Component and end-to-end browser
tests are still outstanding; see KNOWN_LIMITATIONS.

```bash
cd frontend
npm run test        # vitest run
```

## Responsive overflow check

Wide data tables are the usual cause of a phone layout sliding sideways. Before a UI release, audit
every workspace route at 390, 768 and 1440 CSS pixels. An ad-hoc Playwright run does it without
adding a dependency to this repository:

```bash
python3 -m venv /tmp/pwenv && /tmp/pwenv/bin/pip install playwright
```

```python
import asyncio
from playwright.async_api import async_playwright

BASE = "http://localhost:3000/"
ROUTES = ["app", "app/terminal", "app/markets", "app/strategies", "app/copilot", "app/accounts",
          "app/portfolio", "app/analytics", "app/notifications", "app/billing", "app/settings",
          "app/onboarding"]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        for width in (390, 768, 1440):
            context = await browser.new_context(viewport={"width": width, "height": 900})
            page = await context.new_page()
            # sign in here if the routes redirect to /login
            for route in ["", *ROUTES]:
                await page.goto(BASE + route, wait_until="load")
                overflow = await page.evaluate(
                    "() => document.documentElement.scrollWidth"
                    " - document.documentElement.clientWidth"
                )
                print(width, route or "/", "OVERFLOW" if overflow > 2 else "ok", overflow)
            await context.close()
        await browser.close()


asyncio.run(main())
```

Anything reporting more than two pixels is a bug: fix the container (`min-w-0` on the panel, an
explicit `grid-cols-1`, collapsing secondary table columns) rather than hiding the scrollbar.

## Test hygiene rules for contributors

- Never call a real exchange. Use the demo feed, the fake venue (`tests/support/fake_venue.py`,
  installed automatically for every test) or the Deriv mock gateway (`tests/support/deriv_mock.py`).
  The fake venue replaces only the network surface of hosted crypto adapters, so encryption,
  entitlements, audit and error mapping still run for real.
- Never set `VELTRANE_LIVE_TRADING_ENABLED=true` in a test.
- Assert on behaviour, not on log text.
- If a test needs a subscription tier, use the `pro_trader` / `elite_trader` fixtures rather than
  writing rows directly, so the billing path stays covered.
- A failing test that reveals a real bug gets a fix, not a relaxed assertion.

## Manual acceptance walkthrough

Before a release, walk the product as a user:

1. Register, verify, sign in, enable MFA.
2. Connect the simulation venue, sync, confirm balances appear and are labelled simulated.
3. Configure a risk profile, start a paper session, place a buy, then close it.
4. Open the trade detail and confirm entry reason, strategy version, risk checks, fees, slippage
   estimate versus actual, and net P&L after costs are all present.
5. Hit the Free demo limit and confirm the rejection message is clear.
6. Upgrade to Pro through the mock checkout, confirm entitlements change immediately.
7. Attempt live authorisation on a Pro account and confirm each prerequisite is enforced in order.
8. Engage the kill switch and confirm trading stops; release it and confirm trading resumes.
9. Sign in as staff, review revenue, edit a plan price, inspect the audit log.
10. Confirm every screen that shows demo data labels it as simulated.
