# VELTRANE — Architecture

> VELTRANE is a provisional brand name. Domain, trademark and regulatory clearance are **not** complete.

## 1. Product shape

A multi-tenant SaaS for retail traders. Users connect **their own** exchange/broker accounts (read-only or trading-only keys, never withdrawal). The platform never custodies funds.

Four account experiences: **Free / Basic / Pro / Elite**. Monetisation is capability-based; server-side entitlements are the only authority.

## 2. Runtime topology (single deployable unit, no premature microservices)

```
                    ┌───────────────────────────────────────────────┐
   Browser ────────▶│  Next.js 15 (App Router, RSC + client)        │
                    │  Tailwind + shadcn-style primitives, SVG charts│
                    └───────────────┬───────────────────────────────┘
                                    │ HTTPS, Bearer JWT (access) +
                                    │ httpOnly refresh cookie + CSRF
                    ┌───────────────▼───────────────────────────────┐
                    │  FastAPI (app/api/v1)                         │
                    │  ├── auth / users / admin (RBAC)              │
                    │  ├── billing + entitlement service            │
                    │  ├── connections (provider abstraction)       │
                    │  ├── market data (CCXT public + demo feed)     │
                    │  ├── strategies / backtests / paper trading    │
                    │  ├── risk engine (independent, deterministic)  │
                    │  ├── execution gateway (paper | live gated)    │
                    │  └── notifications / audit / analytics         │
                    └───────┬───────────────────┬───────────────────┘
                            │                   │
              ┌─────────────▼──────┐   ┌────────▼─────────────┐
              │ PostgreSQL 17      │   │ Redis 7              │
              │ system of record   │   │ rate limit, cache,   │
              │ (org-scoped rows)  │   │ token revocation,    │
              │                    │   │ kill-switch mirror   │
              └────────────────────┘   └──────────────────────┘
                            │
              ┌─────────────▼──────────────────────────────────┐
              │ Provider adapters                              │
              │  • ccxt (Binance / Bybit / OKX) — crypto       │
              │  • deriv (forex + indices) — scaffolded        │
              │  • paper broker (deterministic simulator)      │
              └────────────────────────────────────────────────┘
```

**Why one backend service:** the workload is a CRUD API plus a scheduled strategy loop. Splitting into microservices would add failure modes and cost without benefit at this stage. The module boundaries (risk, execution, providers, strategies) are enforced in code, not by network hops, so extraction later is mechanical.

## 3. Trust boundaries and control flow for an order

```
AI/strategy signal ──▶ OrderIntent (no side effects)
                          │
                          ▼
        ┌─────────────────────────────────────────────┐
        │ INDEPENDENT RISK ENGINE (pure, deterministic)│
        │  kill switches → permissions → policy rules  │
        │  → sizing/exposure/leverage/day-loss/DD      │
        │  → stop validation → stale data → dupes      │
        └───────────────┬─────────────────────────────┘
             rejected   │   approved
        ┌───────────────▼──────────────┐   ┌──────────▼─────────────┐
        │ risk_decisions + audit log   │   │ Execution Gateway      │
        │ (immutable, no execution)    │   │  paper → simulator     │
        └──────────────────────────────┘   │  live  → adapter       │
                                           │  (requires: global flag,│
                                           │   org live permission,  │
                                           │   checklist, entitlement)│
                                           └────────────────────────┘
```

The risk engine has **no import** from `app.trading` or `app.strategies`; it consumes a plain `RiskContext` dataclass. This is verified by a test that inspects module imports.

## 4. Backend module map

| Path | Responsibility |
|---|---|
| `app/core/config.py` | Typed settings from env; production refuses to boot on insecure defaults |
| `app/core/crypto.py` | Envelope encryption (KEK from env, per-record DEK, AES-256-GCM, AAD binding) |
| `app/core/security.py` | Argon2id hashing, JWT access/refresh, TOTP MFA, token revocation |
| `app/core/rate_limit.py` | Redis fixed-window limiter with in-process fallback |
| `app/db/models/*` | SQLAlchemy 2.0 typed models, org-scoped |
| `app/services/entitlements.py` | Single source of truth for plan limits (server-side) |
| `app/services/billing.py` | Payment abstraction, webhook signature verification, idempotency |
| `app/services/connections.py` | Provider credential lifecycle, sync, no secret egress |
| `app/providers/*` | `BaseProvider` → `CcxtCryptoProvider`, `DerivProvider`, `PaperProvider` |
| `app/risk/engine.py` | Deterministic rule chain + audit of every rejection |
| `app/trading/engine.py` | Order intent lifecycle, duplicate prevention, correlation ids |
| `app/strategies/*` | Strategy interface, versioned library, backtest + walk-forward |
| `app/services/performance_fees.py` | HWM accounting on realised P&L only; disabled by default |
| `app/services/notifications.py` | In-app + email outbox; only confirms executions after commit |
| `app/services/audit.py` | Append-only audit trail |

## 5. Multi-tenancy

* Every tenant-owned table carries `org_id` (non-nullable) and is queried through helpers that inject the caller's org.
* `org_id` is **never** accepted from the request body for tenant data; it is derived from the authenticated session.
* Admin endpoints require `is_staff` + a staff role and are mounted under `/api/v1/admin`; they return aggregated/anonymised data and never plaintext credentials.
* Cross-tenant access attempts return `404` (not `403`) to avoid resource enumeration. Covered by tests.

## 6. Frontend architecture

* Next.js App Router; marketing pages are static, the app shell is client-rendered against the API.
* `lib/api.ts` — typed fetch client with access-token refresh, CSRF header, and error normalisation.
* `lib/format.ts` — money/percent/PnL formatting; every simulated number passes through a `DemoBadge` where relevant.
* Charts are dependency-light SVG components (`components/charts/*`) so the visual language stays consistent and the bundle stays small.
* Design tokens in `app/globals.css` (CSS variables) → Tailwind theme. Midnight navy/charcoal base, champagne-gold accents, platinum neutrals.

## 7. Data flow: paper trading loop

1. User starts a paper session against a strategy version and a connected (or demo) instrument.
2. A tick pulls OHLCV from the market data service (CCXT public or clearly-labelled demo feed). Ticks arrive two ways: on demand from `POST /paper-sessions/{id}/tick`, and unattended from `app/services/scheduler.py`, a single background thread that runs every `VELTRANE_SCHEDULER_INTERVAL_SECONDS` (60 by default) and advances every `running` session. The scheduler is paper-only by construction: it calls the same tick path, which never reaches a live adapter. Its state (`running`, `interval_seconds`, `last_run_at`, `last_summary`) is exposed in `/admin/system/health`.
3. Strategy produces a `Signal`; the engine converts it into an `OrderIntent` with an `idempotency_key`.
4. Risk engine evaluates → `RiskDecision`.
5. Paper broker fills with spread + slippage + fees, writes `orders`, `trades`, `positions`, `fees`, `transactions`, `notifications`, `audit_logs`.
6. Every trade row is addressable at `/trading/trades/{id}` and renders entry reason, strategy version, risk checks, fee/slippage estimate vs actual, net P&L, and human interventions.

`GET /trading/risk-budget` exposes the same headroom the blocking rules will use on the next order
(daily loss, drawdown, account exposure, open positions, consecutive losses, demo executions) so the
terminal can show it before a trader commits. It is read-only and cannot approve anything: the risk
engine remains the only gate.

## 8. Live trading posture (deliberate)

Live execution is **off** in three independent layers:

1. `VELTRANE_LIVE_TRADING_ENABLED=false` (process-wide, default).
2. Per-org `trading_permissions.live_enabled` requires a 3-step flow: acknowledgement of risk document → safety checklist completion → time-delayed confirmation, plus MFA re-auth.
3. Entitlement + provider capability + credential permission check (withdrawal scope present ⇒ hard reject).

Any one failing keeps orders in paper mode. `LIVE_TRADING_ENABLED` cannot be set by an API call; it is env-only and audited at boot.

## 9. Known architectural trade-offs

| Decision | Trade-off |
|---|---|
| Monolith API | Simple to reason about; strategy loop shares CPU with request handling until a worker is split out |
| Postgres-only job state (no Celery yet) | Fewer moving parts; long backtests must be bounded or moved to a worker later |
| In-process scheduler thread | One deployment target, no broker to operate; cannot be scaled past a single scheduler-enabled replica, so a durable worker is the first thing to split out |
| SVG charts | Full visual control, no licence risk; no advanced interactions (crosshair tooltips are basic) |
| Synthetic demo feed | Lets the product be evaluated without credentials; must always be labelled and never presented as market truth |
| ccxt for crypto | Broad coverage, but provider quirks need adapter-level tests before claiming support |
