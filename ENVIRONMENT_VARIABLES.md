# Environment variables

All settings use the `VELTRANE_` prefix and are read by `app/core/config.py` (pydantic-settings,
`extra="ignore"`). Values below are the defaults; anything marked **required** has no safe default
in production.

## Core

| Variable | Default | Notes |
| --- | --- | --- |
| `VELTRANE_ENV` | `development` | `development` \| `test` \| `production` |
| `VELTRANE_SECRET_KEY` | dev placeholder | **required** in production, 32+ chars. Signs JWTs |
| `VELTRANE_MASTER_ENCRYPTION_KEY` | empty | **required** in production. Base64 of 32 bytes. Wraps credential DEKs |
| `VELTRANE_KEK_VERSION` | `1` | Increment when rotating the master key |
| `VELTRANE_DATABASE_URL` | `postgresql+psycopg://DB_USER:DB_PASSWORD@127.0.0.1:5432/veltrane` | **Required.** No default is built in; use a pooled URL in production |
| `POSTGRES_PASSWORD` | `choose-a-local-development-password` | Only read by `docker-compose.yml` to provision the local Postgres container |
| `VELTRANE_REDIS_URL` | `redis://127.0.0.1:6379/0` | Rate limits, cache, token denylist |
| `VELTRANE_API_BASE_URL` | `http://localhost:8000` | Used in email links |
| `VELTRANE_WEB_BASE_URL` | `http://localhost:3000` | Used in email links and redirects |
| `VELTRANE_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated allowlist |
| `VELTRANE_LOG_LEVEL` | `INFO` | Structured JSON logs |

Generate the two secrets with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"                 # secret key
python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())" # master key
```

## Authentication

| Variable | Default | Notes |
| --- | --- | --- |
| `VELTRANE_ACCESS_TOKEN_MINUTES` | `15` | Short on purpose |
| `VELTRANE_REFRESH_TOKEN_DAYS` | `14` | |
| `VELTRANE_REQUIRE_EMAIL_VERIFICATION` | `true` | Leave true in production |
| `VELTRANE_COOKIE_SECURE` | `false` | **must** be true in production |
| `VELTRANE_MFA_ISSUER` | `VELTRANE` | Label shown in authenticator apps |

## Trading and market data

| Variable | Default | Notes |
| --- | --- | --- |
| `VELTRANE_LIVE_TRADING_ENABLED` | `false` | Global execution gate. Keep false until adapters are verified |
| `VELTRANE_DEMO_MARKET_DATA_ENABLED` | `true` | Allows the deterministic feed |
| `VELTRANE_MARKET_DATA_SOURCE` | `ccxt` | `ccxt` (public endpoints) or `demo` |
| `VELTRANE_MARKET_DATA_CACHE_SECONDS` | `20` | |
| `VELTRANE_PAPER_TAKER_FEE_BPS` | `10.0` | Applied to simulated fills |
| `VELTRANE_PAPER_SPREAD_BPS` | `4.0` | Half-spread applied against the trade |
| `VELTRANE_PAPER_SLIPPAGE_BPS` | `3.0` | |
| `VELTRANE_PAPER_STARTING_BALANCE` | `25000` | Paper session default |

## Billing

| Variable | Default | Notes |
| --- | --- | --- |
| `VELTRANE_BILLING_PROVIDER` | `mock` | `mock` or `stripe`. **`mock` is rejected in production** |
| `VELTRANE_STRIPE_SECRET_KEY` | empty | Required when provider is `stripe` |
| `VELTRANE_STRIPE_WEBHOOK_SECRET` | empty | Required when provider is `stripe` |
| `VELTRANE_BILLING_WEBHOOK_TOLERANCE_SECONDS` | `300` | Reject older signatures |

## Bootstrap

| Variable | Default | Notes |
| --- | --- | --- |
| `VELTRANE_ADMIN_EMAIL` | `admin@veltrane.local` | Promoted to owner by `scripts/seed.py` |
| `VELTRANE_ADMIN_PASSWORD` | empty | If set, seed creates the account. Change it at first sign-in |

## Provider credentials

Exchange keys are **not** environment variables. They are entered per subscriber and encrypted at
rest. Only the platform-level KEK lives in the environment.

## Production checklist

`Settings` refuses to start when `VELTRANE_ENV=production` and any of these is wrong:

- `VELTRANE_SECRET_KEY` is the development placeholder or shorter than 32 characters
- `VELTRANE_COOKIE_SECURE` is not true
- `VELTRANE_BILLING_PROVIDER` is `mock`

Set the rest deliberately:

```bash
VELTRANE_ENV=production
VELTRANE_SECRET_KEY=<48+ random chars>
VELTRANE_MASTER_ENCRYPTION_KEY=<base64 of 32 bytes>
VELTRANE_COOKIE_SECURE=true
VELTRANE_REQUIRE_EMAIL_VERIFICATION=true
VELTRANE_LIVE_TRADING_ENABLED=false
VELTRANE_BILLING_PROVIDER=stripe
VELTRANE_STRIPE_SECRET_KEY=sk_live_...
VELTRANE_STRIPE_WEBHOOK_SECRET=whsec_...
VELTRANE_CORS_ORIGINS=https://app.yourdomain.tld
```

Never commit a `.env` file. `.env.example` holds placeholders only.
