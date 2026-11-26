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

**Trading sockets.** Anything that touches an account needs an OTP-authenticated socket. The
session manager (`app/services/deriv_sessions.py`) requests an OTP per account, opens
`wss://.../ws/{demo|real}?otp=...`, and re-authenticates on expiry. Sessions are per connection,
never shared across tenants, and closed explicitly or on process shutdown. Failures are recorded
as auth events and surfaced on the connection.

**Execution.** `app/trading/deriv_execution.py` runs every contract through the same independent
risk engine as any other venue, then through the execution gate (platform switch, live
authorisation, connection permission, session state). Fixed-odds contracts have no traded price,
so the underlying spot is stored as the reference price and the fee is the contract's own spread
(payout below stake). Duplicate submission is prevented with an idempotency key.

**Verification status.** Public market data and contract pricing are verified against the live
gateway. Account authorisation, proposal, buy/sell, close and reconciliation are verified against
a protocol-faithful test server (`tests/support/deriv_mock.py`) with 21 passing integration tests.
They have **not** been verified against a funded Deriv account, so the status stays
`implemented_unverified` and live execution remains behind the platform switch.

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

Crypto payment processors and bank transfer rails are not implemented. The abstraction
(`app/services/billing.py`) takes a provider name and dispatches, so adding one means writing a
verification function and a normaliser, not changing the subscription model.

## Email

`app/services/email.py` writes messages to an outbox table and, when SMTP settings are present,
sends them. No SMTP provider is configured in this repository, so verification and notification
emails are visible only through the outbox (`POST /admin/maintenance/deliver-emails` flushes it).

## Verification checklist before any provider is marked verified

1. Create a read-only API key on the venue; confirm `fetch_balances` and `fetch_positions` return
   the account's real data.
2. Confirm the adapter refuses trading while `allow_trading=False`.
3. Confirm a key with withdrawal permission is rejected by the onboarding guidance and that the
   UI never asks for one.
4. On the venue sandbox, place and cancel an order; reconcile the fill against the venue's own
   record.
5. Record the date, venue, account type and outcome here, and change the status column.
