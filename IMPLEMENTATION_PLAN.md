# Implementation plan

Phases are ordered so that each one leaves a working system. Nothing later is allowed to weaken a
safety control from an earlier phase.

## Phase 1 — Foundation

- [x] Repository layout, `.env` handling, settings with production guards
- [x] SQLAlchemy models (40 tables) and the initial Alembic migration
- [x] Argon2id passwords, email verification, TOTP MFA, refresh rotation with CSRF
- [x] RBAC (owner / analyst / support), tenant isolation helpers, audit log
- [x] Structured logging, request ids, security headers, rate limiting
- [x] Seed script for plans, strategies, flags, risk policy, cost model
- [x] Brand direction and design tokens (documented in `docs/DESIGN_SYSTEM.md`)
- [x] Test harness against real PostgreSQL and Redis

Exit criteria: register → verify → log in → call an authenticated endpoint, with tests.

## Phase 2 — SaaS business

- [x] Plan catalogue with editable prices and limits
- [x] Entitlement service resolving plan limits plus staff overrides
- [x] Billing abstraction, signed mock provider, Stripe adapter, idempotent webhook ledger
- [x] Subscription lifecycle: checkout, active, past due, cancelled, refunded
- [x] Plan change with proration intent and downgrade blocking
- [x] Free-tier limits, including five simulated executions per day
- [x] Admin command centre API: overview, revenue, users, plans, entitlements, audit, flags
- [x] Revenue analytics: MRR, ARR, churn, conversion, revenue by tier, cost per subscriber

Exit criteria: a Free user is refused a paid capability server-side; a Pro upgrade unlocks it
immediately; a replayed webhook changes nothing.

## Phase 3 — Account connections

- [x] Provider protocol with explicit capabilities
- [x] CCXT adapter (Binance, Bybit, OKX) and Deriv scaffold
- [x] Internal paper venue so a user without an exchange can complete onboarding
- [x] Envelope encryption for credentials, key hint, fingerprint, rotation
- [x] Read-only sync of balances, positions and ledger entries
- [x] Safe error handling: failures persist, notify, and never expose secrets
- [x] Portfolio overview excluding simulated balances from live equity

Exit criteria: connect, sync, see balances; a bad key produces a clear error and no leakage.

## Phase 4 — Paper trading and risk

- [x] Strategy interfaces, versioning, approval workflow, limitations field
- [x] Backtest engine with fees, spread, slippage, walk-forward windows, net metrics
- [x] Independent deterministic risk engine with 18 rule families
- [x] Simulated execution with cost modelling and realised P&L
- [x] Immutable trade records with entry reason, strategy version, risk snapshot, slippage
      estimate versus actual, and human intervention notes
- [x] Duplicate-order prevention via idempotency keys
- [x] Kill switches at global, org, provider and user scope
- [x] Notifications for fills, closures, rejections and risk warnings

Exit criteria: an order that violates a limit is rejected, persisted, audited and explained; a
manual close records intervention.

## Phase 5 — Live markets

- [x] Provider-specific adapters with capability reporting
- [x] Market data with demo fallback and explicit `is_demo` labelling
- [ ] **Verified read-only connectivity against real accounts** — requires funded accounts and
      operator time; cannot be done in this environment
- [ ] Verified sandbox order placement per venue

Exit criteria for completion: each provider's status in INTEGRATIONS.md moves to
`verified_read_only` (then `verified_trading`) with a dated note.

## Phase 6 — Controlled live trading

- [x] Multi-step authorisation: entitlement, verified connection, risk acknowledgement, checklist,
      MFA or waiver, cooling-off token
- [x] Platform-wide execution gate re-checked immediately before any venue call
- [x] Risk engine enforcement on the live path with rejection persistence
- [x] Audit of authorisation, revocation, submission and failure
- [x] Kill switches honoured on the live path
- [ ] Independent security review
- [ ] Jurisdiction and regulatory review

The phase stays disabled until the two unchecked items are done. `VELTRANE_LIVE_TRADING_ENABLED`
must remain `false` until then.

## Phase 7 — Commercial launch preparation

- [x] Documentation set (this file and its siblings)
- [x] CI: lint, tests, dependency audit, migration run
- [x] Dockerfile and local compose stack
- [x] Backup and restore procedure documented
- [x] Incident response procedure documented
- [ ] Load and soak testing
- [ ] Payment provider verification in test mode with real cards
- [ ] Terms, privacy policy, risk disclosure documents
- [ ] Support workflow and SLA
- [ ] Production deployment and smoke test

## Deliberately deferred

Microservices, a message queue, a separate execution service, multi-region, and a mobile app are all
deferred. Each adds operational cost that a first cohort does not justify, and each makes the safety
model harder to reason about. The seams are in place (services layer, provider protocol, worker-ready
paper sessions) so they can be split later without a rewrite. The unattended paper scheduler is a
single in-process thread for the same reason: it removes the need for a broker now, and the tick path
it calls is already the seam a real worker would use.

## Budget notes

The development budget target was under $500. This build consumed no paid services: PostgreSQL and
Redis ran locally, market data came from public endpoints and a deterministic feed, and no LLM was
called. The recurring cost of running it is the infrastructure estimate in DEPLOYMENT.md, plus
whatever is spent on an independent security review and legal work — both of which are prerequisites
for launch and cannot be substituted with engineering effort.
