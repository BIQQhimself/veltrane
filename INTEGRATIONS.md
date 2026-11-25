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

## Forex and indices — Deriv

`app/providers/deriv.py`, status `implemented_unverified`.

Deriv's retail API is WebSocket-based and token-authenticated rather than REST. The adapter is
scaffolded with the same interface and reports `trade=False` until the socket flow is implemented
and tested; the API will therefore refuse to route a live order to it. This is deliberate: an
adapter that silently half-works is worse than one that refuses.

Recommended alternative if Deriv integration proves slow: OANDA v20 (REST, well documented) —
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
