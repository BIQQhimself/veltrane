# Threat model

Scope: the VELTRANE application, its database, its provider adapters, and the people who
operate it. Out of scope: exchange-side compromise, subscriber device compromise, and
cryptocurrency network attacks.

Method: enumerate the assets that matter, then the ways they can be harmed, then what the code
actually does about it. "Partial" means a control exists but is incomplete; "Gap" means nothing
meaningful is in place yet.

## Assets

| # | Asset | Why it matters |
| --- | --- | --- |
| A1 | Exchange/broker API credentials | Trade-only keys can still lose a subscriber's balance |
| A2 | Orders, positions, risk limits | Tampering or replay causes direct financial loss |
| A3 | Subscription and entitlement state | Wrong state grants paid capability for free, or blocks a paying user |
| A4 | Payment events and invoices | Forged events grant access; lost events revoke it |
| A5 | Staff accounts | Compromise reaches every tenant |
| A6 | Audit trail | Without it, incidents cannot be reconstructed |
| A7 | Subscriber PII (email, name, country) | Privacy obligations |
| A8 | Performance-fee ledger | Disputes and regulatory exposure |

## Threats

### T1 — Credential exfiltration through the API
*Actor:* authenticated subscriber, compromised session, or malicious insider.
*Path:* call any endpoint that serialises a connection.
*Control:* credentials are never serialised. The model stores ciphertext, a masked hint and a
fingerprint; serialisers (`app/api/serializers.py`) expose only provider, label, status, mode and
timestamps. Admin views omit the hint as well. Test: `test_connections.py` asserts no key or
secret appears in any response.
*Residual risk:* database compromise plus master-key compromise. Mitigated by keeping the KEK
outside the database (environment/secret manager) and rotating it.

### T2 — Credential exfiltration through the database
*Actor:* attacker with SQL read access, or a leaked backup.
*Control:* AES-256-GCM envelope encryption; the KEK is not stored in the database. A backup
alone is useless without the KEK.
*Residual risk:* an attacker with both database and environment access. Documented; requires
host-level compromise.

### T3 — Unauthorised live order submission
*Actor:* subscriber on a low tier, AI strategy bug, compromised session.
*Paths:* direct API call; strategy engine emitting an order; admin mistake.
*Controls:* (a) `live_trading` entitlement is false for Free and Basic; (b) live authorisation
requires a verified read-only sync, risk acknowledgement, 8-item checklist, MFA or waiver, and a
60-second cooling-off token; (c) the process re-reads `VELTRANE_LIVE_TRADING_ENABLED` immediately
before the venue call; (d) the risk engine runs after the entitlement check and can reject; (e)
kill switches at four scopes are checked on every order.
*Residual risk:* a bug in the risk engine. Mitigated by the engine being independent of the AI
layer, deterministic, and covered by unit tests for each rule.

### T4 — Risk-limit bypass by the AI layer
*Actor:* strategy code, prompt injection into a strategy, or a future LLM component.
*Control:* the strategy layer can only produce an `OrderRequest`. Every request passes
`app/risk/engine.py`, which knows nothing about strategies and cannot be configured by them.
Rejections are persisted with failed rule codes and audited. A strategy cannot modify a risk
policy; only an owner can, and each change creates a new version.
*Residual risk:* a strategy that repeatedly submits orders within limits. Mitigated by duplicate
prevention, daily loss limits, and rate limits.

### T5 — Order replay / duplicate submission
*Actor:* client retry, network duplication, malicious replay.
*Control:* `orders.idempotency_key` is unique per organisation; the engine returns the original
order with `idempotent_replay: true`. A duplicate-open-position rule rejects a second entry on the
same instrument and side.
*Residual risk:* an attacker with a valid session can place many *distinct* orders. Bounded by
rate limits and risk caps.

### T6 — Forged billing webhook
*Actor:* anyone who can reach the webhook URL.
*Control:* HMAC verification over the raw body with a timestamp tolerance of 300 seconds; the
mock provider uses the same code path as Stripe. Rejected signatures return 400 and are audited.
Event IDs are unique per provider, so replays are inert.
*Residual risk:* webhook secret leakage. Rotate on suspicion; both providers support it.

### T7 — Entitlement escalation from the client
*Actor:* subscriber editing front-end state or calling endpoints directly.
*Control:* entitlements are resolved server-side from the subscription row and plan limits on
every gated request. There is no client-supplied plan or limit anywhere in the API.
Test: `test_strategies_and_entitlements.py` drives the API directly with a Free account.

### T8 — Cross-tenant access
*Actor:* authenticated subscriber.
*Control:* every read and write filters by the caller's `org_id`; object lookups return 404 on
mismatch. Staff endpoints require a staff role and are namespaced under `/admin`.
Test: `test_tenancy.py` attempts reads and writes across tenants for orders, trades, positions,
connections, notifications, backtests and paper sessions.

### T9 — Staff over-reach
*Actor:* analyst or support staff account.
*Control:* role checks per endpoint. Analysts are read-only. Support cannot change plans, risk,
flags or kill switches. Only owners can price plans, edit risk policy, engage the global kill
switch, or grant the owner role. Every admin action is audited with the actor's email and role.
*Gap:* no four-eyes approval for plan price changes. Tracked for launch.

### T10 — Session theft
*Actor:* network attacker, XSS, malicious extension.
*Control:* short access-token TTL, httpOnly refresh cookie, CSRF double-submit, revocation on
logout, `token_version` invalidation on logout-all and password change, strict CORS.
*Gap:* no device binding or token binding; a stolen access token is usable for up to 15 minutes.

### T11 — Brute force and credential stuffing
*Control:* login rate limit, per-account lockout with audit, uniform error message for unknown
email versus wrong password, argon2id cost.
*Gap:* no CAPTCHA or IP reputation feed.

### T12 — Kill-switch failure
*Control:* four scopes (global, org, provider, user), checked inside order submission rather than
in the UI. The global switch is also mirrored to a Redis key and can be engaged by a file flag so
an operator can stop trading without the web app.
*Gap:* no automatic engagement on loss breach beyond the daily-loss rule. Tracked.

### T13 — Data loss
*Control:* nightly logical backups with retention, documented restore rehearsal, migrations under
version control.
*Gap:* no point-in-time recovery configured yet; requires WAL archiving in production.

### T14 — Performance-fee overcharge
*Control:* realised P&L only, high-water mark per organisation, loss-recovery before further
charges, explicit consent record, jurisdiction gate, full calculation snapshot per record, and a
global setting that keeps the module disabled until legal review is recorded.
*Gap:* the legal review itself. The module is off by default and refuses to enable without a
recorded review reference.

### T15 — Reputational: implying guaranteed returns
*Control:* all performance language is net of modelled costs; demo data is labelled `is_demo` in
every payload and every notification; strategy documents carry a limitations section; the
backtest engine subtracts fees, spread and slippage. The UI must not invent numbers — it renders
only what the API returns.

## Assumptions

- The hosting platform protects environment variables and the filesystem.
- TLS terminates at a trusted proxy; the app sets HSTS in production.
- PostgreSQL and Redis are not exposed to the public internet.
- Subscribers keep their exchange keys trade-only; the platform cannot verify this against the
  exchange until the live adapters are verified with real accounts.

## Open items

Tracked in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md): independent penetration test,
mandatory staff MFA, four-eyes for pricing, WAF, PITR backups, anomaly detection.
