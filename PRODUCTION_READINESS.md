# Production readiness

Status as of this build. A tick means the work is done and verified; a cross means it is not, and
the platform is not ready to take paying customers while any blocking cross remains.

## Blocking items

| # | Item | State | Notes |
| --- | --- | --- | --- |
| 1 | Front end | ◐ | Next.js app with 15 routes, onboarding, admin console and a Deriv terminal exists and is type-checked, but has no design QA on real devices, no browser E2E in CI, and only a thin unit suite |
| 2 | Verified exchange connectivity | ✗ | No adapter has touched a real account. Status is `implemented_unverified` |
| 3 | Independent security review | ✗ | Never performed |
| 4 | Regulatory and legal review | ✗ | Not started; required before live trading or performance fees |
| 5 | Payment provider in live mode | ✗ | Stripe adapter untested against Stripe; mock provider is refused in production, and the Render blueprint runs with billing `off` so checkout refuses instead of granting plans |
| 6 | Terms of service and privacy policy | ✗ | Not drafted |
| 7 | Point-in-time recovery backups | ✗ | Nightly logical dumps only |
| 8 | Mandatory MFA for staff | ✗ | MFA exists but is optional |
| 9 | Load and soak testing | ✗ | No capacity numbers exist |
| 10 | On-call and incident staffing | ✗ | Procedure documented, people not assigned |
| 11 | Deployed environment | ◐ | `render.yaml` (free tier: static site + web service + Postgres) and `DEPLOYMENT_RENDER.md` are prepared and reviewed in-repo, but nothing has been deployed and `corvex.fun` is not connected |
| 12 | Email delivery | ◐ | Outbox, preferences, digests and campaigns are implemented and tested; Resend delivery and its signed webhook are implemented but no message has reached a real inbox. Set `VELTRANE_EMAIL_PROVIDER=resend` with a verified sender and observe one `email.delivered` event |
| 13 | Durable database with backups | ✗ | Render's free Postgres expires 30 days after creation and has no managed backups |
| 14 | Deriv OAuth application | ◐ | Flow, PKCE, state and encrypted credential creation are tested against the protocol mock; no real Deriv application has completed the round trip. Register the app and set the client id and redirect URI |
| 15 | Shared rate-limit store | ◐ | Redis is optional; without it the limiter is per process. Kill switches, entitlements and live gates are database-backed |

## Verified engineering controls

| # | Control | Evidence |
| --- | --- | --- |
| 1 | Registration, verification, login, MFA, refresh rotation, logout, revocation | `tests/test_auth_and_system.py`, `tests/test_security.py` |
| 2 | Tenant isolation on every object route | `tests/test_tenancy.py` (7 resource types) |
| 3 | Server-side entitlements | `tests/test_strategies_and_entitlements.py`, `tests/test_billing.py` |
| 4 | Free tier cannot place live orders | `tests/test_trading.py` |
| 5 | Five simulated executions per day, then refusal — on paper fills and on venue demo contracts | `tests/test_trading.py`, `tests/test_deriv_integration.py` |
| 6 | Demo activity labelled `is_demo` in API payloads and notifications | `tests/test_trading.py`, `tests/test_portfolio_and_notifications.py` |
| 7 | Webhook signature verification and replay protection | `tests/test_billing.py` |
| 8 | Credential encryption and non-disclosure | `tests/test_connections.py` |
| 9 | Risk engine rejects unsafe orders, with reasons | `tests/test_risk_engine.py`, `tests/test_trading.py` |
| 10 | Duplicate prevention on identical terms, not on symbol and side | `tests/test_trading.py`, `tests/test_deriv_integration.py` |
| 11 | Kill switches at four scopes | `tests/test_trading.py`, `tests/test_admin.py` |
| 12 | Admin RBAC and subscriber lockout | `tests/test_admin.py` |
| 13 | Audit trail on auth, orders, risk, billing, admin | asserted across the suite |
| 14 | No real-money order in any test | `VELTRANE_LIVE_TRADING_ENABLED=false` in the harness; live-path tests assert refusal |
| 15 | Live mode requires multi-step authorisation | `tests/test_trading.py` |
| 16 | Trade detail contains costs, slippage, risk checks, intervention | `tests/test_trading.py` |
| 17 | Performance fees blocked without legal review | `tests/test_performance_fees.py` |
| 18 | Production configuration guards (secret, cookies, billing) | `app/core/config.py` validators |
| 19 | Venue execution refuses to run without the platform switch, a live authorisation and a verified connection | `tests/test_deriv_integration.py` |
| 20 | A signal the risk engine refuses is stored rejected, never executed | `tests/test_deriv_autotrade.py` |
| 21 | Schema parity between Alembic head and the ORM models | `tests/test_migrations.py` |
| 22 | Mail is marked sent only on provider acceptance, with idempotency and bounce suppression | `tests/test_email.py` |
| 23 | Email webhooks verified (HMAC, timestamp window) and refused when unconfigured | `tests/test_email.py` |
| 24 | Security and billing notices cannot be switched off, and trade notifications never mail individually | `tests/test_email.py` |
| 25 | Deriv OAuth state is single-use, expiring and hashed at rest; callback is tenant-bound | `tests/test_deriv_oauth.py` |
| 26 | Referral commission counts only verified operator entries; admin endpoints are staff-only | `tests/test_referrals.py` |
| 27 | Fixed-odds exposure is the stake, so position size cannot be bypassed by a one-contract position | `tests/test_deriv_integration.py`, `tests/test_risk_engine.py` |

## Master live-trading switch

The kill switch and the live-trading authorisation flow are not the only gates. Live execution
needs two independent keys:

| Key | Owner | Storage | Effect |
| --- | --- | --- | --- |
| Deployment flag | Whoever operates the host | `VELTRANE_LIVE_TRADING_ENABLED` environment variable | When false, no code path can reach a live adapter, whatever the app says |
| Staff key | Owner/Admin race inside the app | `system_settings` row `live_trading.staff_control` | Can always stop live trading; can only arm it when the deployment flag is on |

Evidence: `app/services/platform_switch.py`, `backend/tests/test_platform_live_switch.py`, and the
`PUT /api/v1/admin/live-trading` endpoint, which requires the typed phrase `ENABLE LIVE TRADING` /
`DISABLE LIVE TRADING`, a written reason, an Owner/Admin role, and writes
`admin.live_trading_switch` to the audit log. A member calling the endpoint receives `404`, matching
the rest of the admin surface.

## Render free-tier topology (prepared, not deployed)

| Component | Target | State |
| --- | --- | --- |
| Frontend | Render Static Site, Next.js `output: "export"`, `corvex.fun` + `www.corvex.fun` | Blueprint + build mode implemented and built locally (`VELTRANE_STATIC_EXPORT=1`) |
| Backend | Render Web Service, uvicorn, migrations at start, `api.corvex.fun` | Blueprint implemented; production guards exercised by tests |
| Database | Render free Postgres | Blueprint implemented; 30-day expiry documented |
| HTTPS | Render-managed certificates | Documented; requires DNS records the owner must add |
| Backend `off` billing mode | `VELTRANE_BILLING_PROVIDER=off` | Implemented and tested: checkout and webhooks answer `503 billing_disabled` |

## Ready to take money?

No. The honest answer is that this is a well-tested backend for a trading product, with the safety
model built before the features rather than bolted on. Taking a subscription payment tomorrow would
mean selling access to an API with no interface, no verified broker connection, and no legal cover.

## Shortest credible path to a first paying cohort

1. Build the front end (marketing, auth, onboarding, terminal, portfolio, billing, admin). This is
   the single largest remaining item.
2. Verify one crypto venue end to end: read-only sync, then sandbox orders, then a small live order
   on a staff-owned account. Record the date in INTEGRATIONS.md.
3. Commission a security review focused on credential handling, authorisation and the live path.
4. Take legal advice on marketing claims, performance fees and the jurisdictions you will accept.
   Keep performance fees disabled until that advice is in hand.
5. Move billing to Stripe in test mode, then live, with webhook replay and failure drills.
6. Enable point-in-time recovery and rehearse a restore.
7. Run a closed beta on Elite only, with live trading still off, to validate paper behaviour and the
   support workflow.

## Honest cost picture

- Infrastructure: ~$25–45/month at list prices for API, database and cache, plus object storage.
- Security review: a focused external review is typically low four figures; it is not optional for a
  product holding trading credentials.
- Legal: terms, privacy, risk disclosures and performance-fee agreements. Also not optional.
- The $500 development budget covered tooling and hosting for development only. It does not and
  cannot cover the three items above.

## What has deliberately not been claimed

- No profitability claim of any kind.
- No claim that any provider integration is operational.
- No fabricated performance figures; the analytics endpoints compute from stored rows and return
  `null` where a denominator is zero.
- No claim of regulatory compliance in any jurisdiction.
