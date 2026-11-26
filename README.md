# VELTRANE

Multi-tenant AI trading SaaS for retail traders. Users connect their **own** exchange and
broker accounts. VELTRANE never custodies funds, never requests withdrawal permission, and
never enables real-money trading by default.

> VELTRANE is a provisional brand name. Trademark, domain and regulatory clearance are not
> complete. Nothing here is financial advice, and no part of this repository claims that any
> strategy is profitable.

## What exists today

| Area | State |
| --- | --- |
| Authentication | Email + password (argon2id), email verification, TOTP MFA, refresh rotation with CSRF, session revocation, account lockout, audit trail |
| Tenancy | Every row is organisation-scoped; cross-tenant reads and writes return 404 |
| Subscriptions | Free / Basic $19 / Pro $49 / Elite $149, prices editable in the admin console, server-side entitlements |
| Billing | Provider abstraction with a signed mock provider and Stripe adapter, idempotent webhooks, past-due grace, cancellation, refunds, invoices, payments |
| Connections | Provider registry (Binance, Bybit, OKX, Deriv, simulation venue), envelope-encrypted credentials, read-only sync, safe error handling |
| Market data | Public CCXT tickers/candles with a deterministic demo feed fallback. Every payload carries `is_demo` |
| Strategies | Versioned strategies with entry/exit rules, risk parameters, limitations, walk-forward backtests net of fees, approval workflow |
| Paper trading | Simulated execution with taker fees, spread, slippage, realised P&L after costs, immutable trade records |
| Risk engine | Independent deterministic engine, 20+ checks, rejections audited, kill switches at global/org/provider/user scope |
| Live trading | Code paths exist and are gated: entitlement, verified trade-only connection, risk acknowledgement, 8-item checklist, MFA or written waiver, 60-second cooling-off token, platform flag. Off by default |
| Admin | Owner/analyst/support RBAC, revenue and cost analytics, plan and entitlement management, risk policy versioning, kill switches, flags, audit log, support inbox, fraud signals |
| Performance fees | Elite-only, high-water-mark accounting, realised P&L only, consent records, jurisdiction gate, disabled until legal review is recorded |
| Web app | Next.js 15 App Router + TypeScript + Tailwind. Twelve workspace screens (overview, terminal, markets, strategies, copilot, accounts, portfolio, analytics, notifications, billing, settings, onboarding), an admin console, and an installable PWA shell |
| Tests | 151 backend tests against real PostgreSQL and Redis, plus a frontend unit suite (Vitest) started with the chart scale and demo-feed invariants |

## What does **not** exist yet

Native iOS and Android apps (the web app is installable as a PWA instead), verified live exchange
connectivity, a payment provider in live mode, a scheduler that runs strategies unattended
autonomously, performance/load testing, an independent security review, and the legal work for
performance fees. See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) and
[PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

## Repository layout

```
frontend/                Next.js app (App Router, React 19, Tailwind), design tokens in
                         src/app/globals.css + tailwind.config.ts, Vitest unit suite
backend/                 FastAPI application, Alembic migrations, pytest suite
  app/api/v1/            HTTP routers (auth, billing, connections, markets, strategies,
                         trading, portfolio, analytics, notifications, admin, health)
  app/services/          Domain services (entitlements, billing, risk glue, audit, …)
  app/risk/              Independent deterministic risk engine and rules
  app/strategies/        Strategy interfaces, indicators, backtest engine
  app/providers/         Exchange/broker adapters behind one protocol
  app/db/models/         SQLAlchemy models (40 tables)
  alembic/               Schema migrations
  tests/                 Integration tests against Postgres + Redis
docs/                    Extended notes (API map, UI direction)
ARCHITECTURE.md          System design
```

## Run it locally

Prerequisites: Python 3.13, PostgreSQL 17, Redis 7.

```bash
# 1. Database
createdb veltrane && createuser veltrane --pwprompt   # pick any local password

# 2. Backend
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp ../.env.example ../.env          # then edit values
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed.py    # plans, strategies, flags, risk policy, cost model
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Health check: `curl http://localhost:8000/api/v1/health`.

Create the first staff account with `VELTRANE_ADMIN_EMAIL` and `VELTRANE_ADMIN_PASSWORD` set,
then run `backend/scripts/seed.py`; the script promotes that address to owner. Change the
password immediately after first sign-in.

## Tests

```bash
cd backend
createdb veltrane_test
.venv/bin/python -m pytest            # 128 tests
.venv/bin/python -m pytest -k risk    # one slice
```

Tests run against real PostgreSQL and Redis, with the demo market feed, and never submit a
real-money order. Live-trading tests assert that execution stays blocked.

## Safety rules enforced in code

1. `VELTRANE_LIVE_TRADING_ENABLED=false` by default; the process re-checks the flag immediately
   before any venue call.
2. Free and Basic plans have `live_trading: false`; the check is server-side.
3. Live authorisation needs a verified connection, an 8-item checklist, a risk acknowledgement,
   MFA (or a written waiver), and a 60-second cooling-off confirmation token.
4. Every order — paper or live — is evaluated by the risk engine. AI output cannot bypass it.
5. Kill switches work at four scopes and are checked on every order; the global switch can also
   be engaged from a file flag (`KILL_SWITCH` file) so it works when the app UI is unavailable.
6. Rejected orders are persisted with the failed rule codes and audited.
7. Exchange credentials are envelope-encrypted (AES-256-GCM under a KEK) and never returned by
   any API, including the admin surface.

## Documentation

[ARCHITECTURE](ARCHITECTURE.md) · [IMPLEMENTATION_PLAN](IMPLEMENTATION_PLAN.md) ·
[SECURITY](SECURITY.md) · [THREAT_MODEL](THREAT_MODEL.md) ·
[TRADING_RISK_POLICY](TRADING_RISK_POLICY.md) · [INTEGRATIONS](INTEGRATIONS.md) ·
[SUBSCRIPTIONS](SUBSCRIPTIONS.md) · [DATABASE_SCHEMA](DATABASE_SCHEMA.md) ·
[DEPLOYMENT](DEPLOYMENT.md) · [ENVIRONMENT_VARIABLES](ENVIRONMENT_VARIABLES.md) ·
[TESTING](TESTING.md) · [KNOWN_LIMITATIONS](KNOWN_LIMITATIONS.md) ·
[PRODUCTION_READINESS](PRODUCTION_READINESS.md)
