# Security

This document describes what is implemented, what is assumed, and what still needs
independent review. It is written to be auditable rather than reassuring.

## 1. Threat model summary

The full table lives in [THREAT_MODEL.md](THREAT_MODEL.md). The four assets that matter:

1. **Subscriber exchange credentials** — trade-only keys. Leakage enables unauthorised trading.
2. **Subscriber trading state** — orders, positions, risk limits. Tampering causes financial loss.
3. **Billing state** — entitlements, invoices, refunds. Tampering causes revenue loss or wrongful access.
4. **Operator access** — staff roles. Compromise exposes every tenant.

Funds are never custodied. The platform cannot move money out of a subscriber account because
withdrawal permission is prohibited by product design and by the onboarding checklist.

## 2. Authentication

- Passwords are hashed with **argon2id** (`time_cost=3`, `memory_cost=65536`, `parallelism=2`).
  Minimum 12 characters with mixed case, digit and symbol; enforced server-side.
- Email verification is required before sign-in (`VELTRANE_REQUIRE_EMAIL_VERIFICATION=true`).
- TOTP MFA is available. The shared secret is encrypted at rest with the same envelope scheme as
  exchange credentials and is never returned after setup completes.
- Failed logins increment a counter and lock the account temporarily; failures are audited with
  IP and user agent.
- Access tokens are short-lived JWTs (15 minutes) carrying `sub`, `org`, `jti`, `ver`.
  Refresh tokens are rotated on every use and stored hashed.
- Refresh uses an httpOnly, SameSite=Lax cookie plus a double-submit CSRF token. A refresh
  without a matching `X-CSRF-Token` header is rejected.
- **Session revocation**: `POST /auth/logout` denylists the presented access-token `jti` in
  Redis until natural expiry. `POST /auth/logout-all` and password changes increment
  `users.token_version`, which invalidates every previously issued token.
- Production configuration refuses to start with the development secret, without
  `VELTRANE_COOKIE_SECURE=true`, or with the mock billing provider.

## 3. Authorisation and tenancy

- Every query is scoped by `org_id` taken from the authenticated user, never from the request
  body. Cross-tenant object access returns 404 rather than 403 so existence is not disclosed.
- Staff endpoints live under `/api/v1/admin` and require a staff role. `owner` is required for
  role changes, risk policy edits, kill switches and plan pricing. `analyst` is read-only.
  `support` can read users and reply to tickets. Subscribers receive 404 on the whole surface.
- A staff member cannot promote anyone to `owner`; only an existing owner can do that, and the
  endpoint refuses self-escalation of the `owner` role.
- Entitlements are resolved server-side on every request that needs them. The front end may hide
  a button, but hiding is never the control.

## 4. Credential handling

- Exchange API keys and secrets are encrypted with AES-256-GCM under a per-credential data key,
  which is itself encrypted by the master key (envelope encryption, `app/core/crypto.py`).
- Only a masked hint (last four characters) and a SHA-256 fingerprint are stored in clear.
- No endpoint returns secret material — not the subscriber API, not the admin API. The admin
  connection view deliberately omits `key_hint` too.
- Revoking a connection deletes its credential row. Rotating replaces the ciphertext.
- In non-production the master key may be generated per process; credentials then become
  unreadable after restart, which is intentional friction against accidental reuse of dev data.
- Withdrawal permission is never requested. The onboarding checklist requires the user to attest
  that their key is trade-only, and the attestation is stored on the connection.

## 5. Billing integrity

- Subscription state changes only through a signature-verified provider webhook. The mock
  provider signs `timestamp.body` with HMAC-SHA256 and enforces a 300-second tolerance. Stripe
  uses its `t=…,v1=…` scheme over the raw body.
- Webhook events are stored by `(provider, event_id)` with a unique constraint; replays return
  `already_processed` and never double-charge or double-grant.
- A front-end "payment succeeded" message cannot activate anything. The mock completion endpoint
  exists only to drive the local test path and is disabled in production.
- Refunds are staff-only, cannot exceed the captured payment, and are audited.
- Card data never touches this system; the payment provider holds it.

## 6. Transport and headers

`SecurityHeadersMiddleware` sets `X-Content-Type-Options`, `X-Frame-Options: DENY`,
`Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy` and, in production,
HSTS. API responses are `Cache-Control: no-store`. CORS is an explicit allowlist from
`VELTRANE_CORS_ORIGINS`; credentials are allowed only for those origins.

## 7. Rate limiting and abuse

Redis-backed fixed-window limits with an in-memory fallback: 600 requests/minute per client
globally, 10 login attempts per 5 minutes per client, and tighter limits on registration,
password reset and order submission. Exceeding a limit returns 429 with a coded error.

## 8. Input validation and error handling

All request bodies are Pydantic models with bounded fields. UUID path parameters are validated
before hitting the database, and a SQLAlchemy `StatementError` handler converts malformed
identifiers into a clean 400. Unhandled exceptions return a generic
`internal_error` payload; stack traces are logged, never returned. Validation errors expose
field locations and messages only.

## 9. Audit trail

`audit_logs` records authentication events, order intent, fills, rejections, trade closure,
connection changes, billing events, admin actions, consent and configuration changes, with
actor, org, IP, user agent and a JSON payload. Audit rows are written in the same transaction as
the change they describe, and the failed-login path commits explicitly so the record survives the
request.

## 10. Secrets management

- All configuration comes from environment variables (`VELTRANE_*`), never from code.
- `.env` is git-ignored; `.env.example` contains placeholders only.
- Production requires `VELTRANE_SECRET_KEY` (32+ chars) and `VELTRANE_MASTER_ENCRYPTION_KEY`
  (base64 of 32 bytes). Rotate the KEK with `kek_version` and a re-encryption migration before
  retiring an old key.
- Provider API secrets for Stripe are read from the environment and never logged.
- `VELTRANE_DATABASE_URL` has no built-in default: a missing value fails at start-up instead of
  silently connecting with a shipped password. `docker-compose.yml` reads `POSTGRES_PASSWORD`
  from the environment for the same reason.
- Setting values are never echoed in configuration errors (`hide_input_in_errors`), so a
  misconfigured deployment cannot leak a secret into logs.
- This repository is public. Values that remain in code are deliberately non-secret:
  the ephemeral Postgres password in `.github/workflows/ci.yml`, fake exchange keys in test
  fixtures, and the password the test suite assigns to accounts it creates. None of them
  authenticate to anything outside a disposable CI container or test database.

## 11. Dependency and supply chain

Dependencies are pinned in `backend/requirements.txt`. Run
`pip-audit -r backend/requirements.txt` before each release and record the result in the release
notes. No dependency is loaded from a non-standard index.

## 12. Backup and recovery

See [DEPLOYMENT.md](DEPLOYMENT.md#backups). Summary: nightly `pg_dump` to object storage with
30-day retention, weekly restore rehearsal into a scratch database, Redis treated as ephemeral
(rate limits, cache, token denylist) with the consequence that a Redis loss re-enables previously
revoked short-lived tokens until they expire — acceptable given the 15-minute access-token TTL,
and documented rather than hidden.

## 13. Known gaps

- No independent penetration test or code audit has been performed.
- No WAF or bot mitigation in front of the API.
- MFA is optional; staff accounts should be required to use it before production launch
  (tracked in PRODUCTION_READINESS.md).
- Email delivery is a database outbox; an SMTP/API transport must be configured and monitored.
- There is no anomaly detection on trading behaviour beyond the fraud signals dashboard.
