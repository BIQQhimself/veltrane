# Testing

## Running the backend suite

```bash
cd backend
createdb veltrane_test                      # once
.venv/bin/python -m pytest                  # 128 tests, ~45 s
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
| `test_auth.py` | Registration, verification, login, MFA, refresh rotation, logout, password reset |
| `test_billing.py` | Plans, checkout, webhook verification and replay, plan change, cancellation, invoices |
| `test_connections.py` | Provider listing, connection creation, credential encryption, sync, error handling, no secret leakage |
| `test_tenancy.py` | Cross-tenant reads and writes return 404 for orders, trades, positions, connections, notifications, backtests, paper sessions |
| `test_strategies_and_entitlements.py` | Strategy catalogue, versioning and approval, backtests, paper sessions, entitlement gating by tier |
| `test_risk_engine.py` | Each rule in isolation, and the composition of rules into a decision |
| `test_trading.py` | Order submission, risk rejection, duplicate prevention, fills, fees, P&L, close, cancel, kill switches, live gating |
| `test_admin.py` | RBAC, overview and revenue, plan editing, risk policy versioning, kill switches, flags, audit, support, costs |
| `test_performance_fees.py` | HWM accounting, loss recovery, legal-review gate, consent, invoicing |
| `test_portfolio_and_notifications.py` | Portfolio overview and performance, notification feed, order and trade notifications, support tickets, settings |
| `test_security.py` | Headers, password hashing, login rate limit, token tampering, CSRF, MFA secret at rest, error hygiene, session revocation |

## Safety invariants asserted by tests

These are not aspirations; each is checked.

1. A Free account cannot place a live order, whatever it sends (`test_trading.py`).
2. Live execution is refused while `VELTRANE_LIVE_TRADING_ENABLED=false`, even for an authorised
   Elite account with a verified connection.
3. The fifth simulated execution succeeds and the sixth is rejected on the Free tier.
4. Every order — accepted or rejected — has a `risk_decisions` row and an audit entry.
5. A repeated idempotency key returns the original order and does not create a second fill.
6. Engaging the kill switch at any scope blocks the next order; releasing it restores trading.
7. An expired or forged webhook signature changes nothing.
8. No API response contains a credential, a key hint for another tenant, or a password hash.
9. Cross-tenant object access returns 404, not 403 and not data.
10. A non-staff account gets 404 on every admin route.
11. Performance fees cannot be enabled without a recorded legal review.
12. Paper trades are marked `is_demo: true` and excluded from live equity.

## Frontend tests

The front end is checked with TypeScript (`npm run typecheck`), ESLint (`npm run lint`) and a
production build (`npm run build`) in CI. Component tests are not written yet; see
KNOWN_LIMITATIONS.

## Test hygiene rules for contributors

- Never call a real exchange. Use the demo feed or a fake provider.
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
