# Integrations

Status vocabulary used here, and enforced by `app/providers/registry.py`:

| Status | Meaning |
| --- | --- |
| `implemented_unverified` | Code exists and is unit-tested against fakes, but has never touched the real venue |
| `verified_read_only` | Authenticated read-only calls have been observed working against a real account |
| `verified_trading` | A real order has been placed and reconciled on a funded account |
| `simulated` | Not a venue at all — the internal paper venue |

**Nothing in this repository is `verified_trading`.** No funded account was used during
development, and no real-money order was submitted at any point. Anything below that is not
marked verified must be treated as untested against the real world.

## Provider abstraction

`app/providers/base.py` defines a small protocol — `test_connection`, `fetch_balances`,
`fetch_positions`, `fetch_markets`, `place_order`, `cancel_order`, `fetch_order` — plus a
`ProviderCapabilities` record. Adapters declare what they support rather than pretending all
venues are identical:

```python
ProviderCapabilities(
    read=True, trade=False, cancel=False,
    oauth=False, markets={...}, notes="..."
)
```

The registry (`app/providers/registry.py`) maps provider codes to adapters and capabilities. The
API exposes capabilities so the UI can disable an action that the venue cannot perform.

## Cryptocurrency — CCXT

Shared implementation: `app/providers/ccxt_provider.py`.

| Provider | Code | Read | Trade | Markets | Status |
| --- | --- | --- | --- | --- | --- |
| Binance | `binance` | yes | yes (gated) | spot, perpetual futures | `implemented_unverified` |
| Bybit | `bybit` | yes | yes (gated) | spot, linear perpetual | `implemented_unverified` |
| OKX | `okx` | yes | yes (gated) | spot, swap | `implemented_unverified` |

- Keys are used with `defaultType` set per market and `enableRateLimit=True`.
- Sandbox support exists for Binance via `set_sandbox_mode(True)`; the sandbox path is what should
  be used for the first real connectivity test.
- Errors are normalised into `ProviderError(code, message, retryable)`; a venue error never
  propagates a stack trace or a credential to the client.
- Read-only enforcement: an adapter is constructed with `allow_trading=False` unless the caller
  holds the live-trading entitlement, a verified connection and an active authorisation.

## Forex, indices and synthetics — Deriv

`app/providers/deriv.py`, status `implemented_unverified`.

Deriv is a broker, not an exchange: retail instruments are fixed-odds and multiplier contracts
rather than a central order book, and the API is REST plus WebSocket rather than plain REST.
The adapter is built against Deriv's current API (`api.derivws.com`):

| Concern | Endpoint | Authentication |
| --- | --- | --- |
| Tradable symbols, candles, ticks | public gateway WebSocket | none |
| Contract pricing (`proposal`) | trading socket | OTP |
| Buy / sell / portfolio / statement | trading socket | OTP |
| Account list, OTP issuance | `POST /trading/v1/options/accounts/{id}/otp` | Personal Access Token or OAuth 2.0 |

**Authentication.** A single Personal Access Token (or an OAuth 2.0 access token) is the whole
credential. Deriv has no API secret, and asking users for one was a defect in the original
scaffold. `provider_catalog()` therefore publishes `requires_api_secret: false` and
`requires_app_id: true`, and the connect form renders fields from that metadata instead of
hardcoding key/secret inputs. Tokens are requested with read and trade scopes only; withdrawal
scope is never requested and the adapter has no withdrawal code path.

**OAuth 2.0 authorisation.** The preferred path is the authorization-code flow with PKCE, so
VELTRANE never handles a Deriv password and the user can revoke access from Deriv's own
dashboard. `app/services/deriv_oauth.py` builds the authorisation URL, stores a single-use
state row (`deriv_oauth_states`, hashed, with a TTL), and exchanges the code server-side. The
requested scopes are `trade account_manage`; `payment` is never requested because it permits
withdrawals, and `application_read` is unnecessary. Deriv issues **no refresh token**, so an
expired access token surfaces as "reconnect needed" on the connection rather than silently
failing syncs.

Two product rules are enforced in code, not just in the UI:

- **One connection follows one Deriv account.** A Deriv authorisation can expose both a demo
  and a real account. VELTRANE stores both in the connection's metadata, but only one is active
  at a time; switching account type reuses the same connection row, so a user cannot end up with
  duplicate profiles, duplicate risk budgets or duplicate positions.
- **Connecting is not authorising trading.** An OAuth token grants API access. Live execution
  still requires the platform switch, the live-trading authorisation, a trading-permission
  connection and a passing risk decision.

A Personal Access Token remains available as a manual fallback for users whose Deriv account
predates the application registration, and for self-hosted deployments without an OAuth app.

**Referral programme.** People who reach VELTRANE without a Deriv account can open the
configured partner link from the accounts page. The link is validated as HTTPS and must carry a
Deriv tracking parameter (`t`, `affiliate_token`, `sidi` or `ca`); anything else is rejected, so
a mistyped link cannot silently lose attribution. Clicks are recorded once per opaque visitor id
(`referral_events`, kind `click`) and a registration is attributed when the browser presents the
same id (`kind=registration`). Commission is **never inferred**: only an operator-recorded,
verified figure from the Deriv partner statement is counted, and the funnel labels estimated
values as unverified. See `SUBSCRIPTIONS.md` for how this sits alongside performance fees.

**Trading sockets.** Anything that touches an account needs an OTP-authenticated socket. The
session manager (`app/services/deriv_sessions.py`) requests an OTP per account, opens
`wss://.../ws/{demo|real}?otp=...`, and re-authenticates on expiry. Sessions are per connection,
never shared across tenants, and closed explicitly or on process shutdown. Failures are recorded
as auth events and surfaced on the connection.

**Execution.** `app/trading/deriv_execution.py` runs every contract through the same independent
risk engine as any other venue, then through the execution gate (platform switch, live
authorisation, connection permission, session state). Fixed-odds contracts have no traded price,
so the underlying spot is stored as the reference price and the fee is the contract's own spread
(payout below stake). Two contracts are duplicates only when every term matches — instrument,
side, contract type, stake and duration; an idempotency key derived from those terms prevents a
double submission of the same intent, while a genuinely different contract is priced and assessed
on its own. A contract opened on a demo account counts against the subscriber's daily simulated
execution allowance, exactly like a paper fill.

**Venue error mapping.** Deriv's status codes are translated rather than passed through:
`401` becomes `invalid_token` (or `app_id_required` when the response names the App-ID header),
`403` becomes `missing_scope`, `402` becomes `payment_required` with the three causes worth
checking — App ID mismatch, a token without read/trade scope, or an account with no balance —
and `429` becomes a retryable rate limit. Every message says that nothing was sent to the venue.
`402` in particular is a credential/account problem, not a balance the platform can top up.

**Verification status.** Public market data and contract pricing are verified against the live
gateway (`tests/test_deriv_live_market_data.py`, opt-in). Account authorisation, proposal,
buy/sell, close, reconciliation and the scheduled runner are verified against a protocol-faithful
test server (`tests/support/deriv_mock.py`, `tests/test_deriv_integration.py`,
`tests/test_deriv_provider.py`, `tests/test_deriv_autotrade.py`). They have **not** been verified
against a funded Deriv account, so the status stays `implemented_unverified` and live execution
remains behind the platform switch.

If Deriv proves unreliable in production, OANDA v20 (REST, well documented) is the fallback —
not implemented.

## Simulation venue — `paper`

`app/providers/paper.py`, status `simulated`, `trade=False` in the provider capability table
because it never touches a venue; execution is handled internally by
`app/trading/engine.py`. It exists so a new subscriber can complete the connection flow, see
balances and positions, and run strategies without an exchange account. Balances created by this
provider are excluded from live portfolio equity.

## Market data

- `VELTRANE_MARKET_DATA_SOURCE=ccxt` uses public endpoints (no keys) for tickers and OHLCV, with a
  20-second cache in Redis.
- `VELTRANE_MARKET_DATA_SOURCE=demo` uses a deterministic feed seeded per instrument, so tests and
  offline development are reproducible. Every quote carries `is_demo: true`.
- If CCXT fails, the API falls back to the demo feed and marks the response as demo rather than
  returning stale data silently.

## Payments

| Provider | Code | Status |
| --- | --- | --- |
| Signed mock (local/CI only) | `mock` | working, deliberately disabled in production |
| Stripe Checkout + webhooks | `stripe` | implemented, not exercised against a live Stripe account |
| SPay (Nigeria) | `spay` | **evaluated, not implemented — blocked on server-side verification** |

Crypto payment processors and bank transfer rails are not implemented. The abstraction
(`app/services/billing.py`) takes a provider name and dispatches, so adding one means writing a
verification function and a normaliser, not changing the subscription model.

### SPay — evaluation result (2026-11)

Requested for NGN card, transfer and USSD subscriptions. Reviewed against the published
documentation at <https://spay.readme.io>. Findings:

| Requirement | Documented by SPay? | Evidence |
| --- | --- | --- |
| Nigerian card payments | Yes | Accept Payments lists "Pay with Cards" as a payment option |
| Bank transfer and USSD | Yes | Accept Payments lists "Pay with USSD" and "Pay with Transfer" |
| Monthly recurring card subscriptions | Yes, via dashboard-created subscription links | Subscription: "A created subscription link has recurring functionality built into it" |
| Plans and hosted payment links | Yes, created in the SPay dashboard, not via API | Payment Link: "This feature enables business owners who do not own websites receive single or recurring payments" |
| NGN only | Yes | Accept Payments: `currency` — "Allowed values is: NGN." |
| Test mode | Yes | Test Payment page + `testcheckout.spaybusiness.com` in the sample code |
| Server-side transaction verification | **No** | The only documented confirmation is the browser `callback`; no verify endpoint is published, and the docs contain no API reference section ("No API Endpoints") |
| Authenticated payment/renewal notifications (webhooks) | **No** | No webhook page exists; the documented outcome of a payment is "you will receive a mail and their details will also reflect on your dashboard" |
| Failed renewal handling | **No** | Not documented; no API for renewal state |
| Cancellation | **No** | Not documented; no API |
| Refund support | **No** | Not documented |

**Why this blocks implementation.** Two non-negotiable rules in this repository are "a frontend
payment-succeeded message is never trusted" and "entitlements change only after a
signature-verified provider event is persisted". SPay documents neither a verification endpoint
nor signed notifications, so there is no way to satisfy them: the only signal SPay publishes is a
JavaScript callback running in the customer's browser, which any visitor can fabricate with
developer tools. Granting a plan on that signal would hand out paid tiers for free.

**What is needed before this can be built** (either one unblocks it):

1. SPay supplies server-side documentation and test credentials for: transaction lookup by
   reference, webhook signing (secret + algorithm), subscription/renewal status, cancellation and
   refund. Then a `SpayProvider` fits the existing `BillingProvider` interface: `create_checkout`
   returns the hosted link, `verify_*` implements the lookup, and `process_webhook` reuses the
   existing idempotency table.
2. Written approval of a lower-assurance design (for example: activation only after an operator
   confirms each payment in the SPay dashboard). That is a business decision, not a technical one.

Until one of those exists, `VELTRANE_BILLING_PROVIDER` stays `off` and no NGN price, plan limit or
entitlement has been changed.

## Email — outbox and Resend

`app/services/email.py` is the single write path for outbound mail. Every message is first stored
in `email_outbox` with a rendered subject, HTML and plain text, then delivered by the scheduler
loop or by `POST /admin/maintenance/deliver-emails`.

| Provider | Behaviour | Status |
| --- | --- | --- |
| `outbox` (default) | Records the message and sends nothing. The record keeps `provider_status=outbox_only` and no `sent_at` | verified by tests |
| `resend` | `POST https://api.resend.com/emails` with the outbox row id as `Idempotency-Key` | implemented, not verified against a live Resend account |

Rules the implementation holds to:

- **Nothing is marked sent unless the provider accepted it.** `sent_at` and
  `provider_message_id` are written only after a 2xx response. A 429 or 5xx leaves the row
  `queued` with exponential backoff; a 4xx other than 429 marks it `failed` and stops retrying.
- **A bounced address is suppressed.** Once a row reaches `bounced` or `complained`, later mail to
  that address is stored as `suppressed` rather than sent.
- **Webhooks are verified, not trusted.** `POST /api/v1/webhooks/resend` checks the Svix HMAC
  over `svix-id.svix-timestamp.body`, rejects timestamps older than five minutes, and refuses
  everything with `401 webhook_not_configured` when no secret is set. Delivery, bounce and
  complaint events are appended to the row's event history.
- **Preferences are honoured at queue time.** `notification_preferences` decides whether a
  category produces an email at all; security and billing cannot be switched off. Individual
  trade notifications never generate an email — they stay in the app, and the daily digest is
  the only trading mail.

Status: `implemented_unverified` for Resend until a message is delivered to a real inbox and its
`email.delivered` webhook is observed.

## Verification checklist before any provider is marked verified

1. Create a read-only API key on the venue; confirm `fetch_balances` and `fetch_positions` return
   the account's real data.
2. Confirm the adapter refuses trading while `allow_trading=False`.
3. Confirm a key with withdrawal permission is rejected by the onboarding guidance and that the
   UI never asks for one.
4. On the venue sandbox, place and cancel an order; reconcile the fill against the venue's own
   record.
5. Record the date, venue, account type and outcome here, and change the status column.
