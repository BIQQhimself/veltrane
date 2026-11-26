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
| `VELTRANE_DATABASE_URL` | `postgresql+psycopg://DB_USER:DB_PASSWORD@127.0.0.1:5432/veltrane` | **Required.** No default is built in; use a pooled URL in production. `postgres://` and `postgresql://` are accepted and rewritten to the psycopg 3 driver, which is what managed hosts hand out |
| `VELTRANE_DB_POOL_SIZE` | `10` | SQLAlchemy pool per process. Lower it when the database caps connections |
| `VELTRANE_DB_MAX_OVERFLOW` | `20` | Extra connections above the pool size |
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
| `VELTRANE_COOKIE_SAMESITE` | `lax` | `lax`, `strict` or `none`. `none` requires `VELTRANE_COOKIE_SECURE=true`; use it only when web and API sit on different sites. `corvex.fun` + `api.corvex.fun` are one site, so `lax` is correct |
| `VELTRANE_TRUSTED_PROXIES` | `127.0.0.1,::1` | Peers allowed to set `X-Forwarded-For`. Comma list of addresses, CIDR blocks, or `*`. `*` is only correct when nothing can reach the process except the platform proxy (Render does this) |
| `VELTRANE_MFA_ISSUER` | `VELTRANE` | Label shown in authenticator apps |

## Trading and market data

| Variable | Default | Notes |
| --- | --- | --- |
| `VELTRANE_LIVE_TRADING_ENABLED` | `false` | Global execution gate. Keep false until adapters are verified |
| `VELTRANE_SCHEDULER_ENABLED` | `true` | Runs the unattended paper-session ticker. Paper only; it has no path to a live adapter. Set `false` on every replica except one |
| `VELTRANE_SCHEDULER_INTERVAL_SECONDS` | `60` | How often the paper ticker looks for due sessions |
| `VELTRANE_DEMO_MARKET_DATA_ENABLED` | `true` | Allows the deterministic feed |
| `VELTRANE_MARKET_DATA_SOURCE` | `ccxt` | `ccxt` (public endpoints) or `demo` |
| `VELTRANE_MARKET_DATA_CACHE_SECONDS` | `20` | |
| `VELTRANE_PAPER_TAKER_FEE_BPS` | `10.0` | Applied to simulated fills |
| `VELTRANE_PAPER_SPREAD_BPS` | `4.0` | Half-spread applied against the trade |
| `VELTRANE_PAPER_SLIPPAGE_BPS` | `3.0` | |
| `VELTRANE_PAPER_STARTING_BALANCE` | `25000` | Paper session default |
| `VELTRANE_DERIV_REST_BASE` | `https://api.derivws.com` | Deriv REST base. Overridable so tests can point at a local gateway |
| `VELTRANE_DERIV_PUBLIC_WS_URL` | `wss://api.derivws.com/trading/v1/options/ws/public` | Unauthenticated market-data and pricing socket |
| `VELTRANE_DERIV_APP_ID` | *(empty)* | Deriv application id sent as `Deriv-App-ID` for Personal Access Token auth. Required for token connections; OAuth tokens carry the app themselves |
| `VELTRANE_DERIV_OAUTH_CLIENT_ID` | *(empty)* | Enables the OAuth 2.0 authorization-code flow when set with the redirect URI |
| `VELTRANE_DERIV_OAUTH_REDIRECT_URI` | *(empty)* | Must match the redirect registered with Deriv |
| `VELTRANE_DERIV_OAUTH_AUTH_URL` | `https://auth.deriv.com/oauth2/auth` | Authorization endpoint |
| `VELTRANE_DERIV_OAUTH_TOKEN_URL` | `https://auth.deriv.com/oauth2/token` | Token endpoint |
| `VELTRANE_DERIV_SESSION_MAX_FAILURES` | `5` | Consecutive socket/auth failures before a connection is marked errored and needs a manual reconnect |
| `VELTRANE_DERIV_AUTOTRADE_RUNNER_ENABLED` | `true` | Runs the autotrade signal generator in the scheduler. It proposes only; the risk engine still decides |
| `VELTRANE_DERIV_AUTOTRADE_INTERVAL_SECONDS` | `120` | How often the autotrade runner evaluates each enabled config |

## Billing

| Variable | Default | Notes |
| --- | --- | --- |
| `VELTRANE_BILLING_PROVIDER` | `mock` | `mock`, `stripe` or `off`. **`mock` is rejected in production.** `off` keeps the abstraction and refuses checkout with `503 billing_disabled` instead of granting paid plans for free |
| `VELTRANE_STRIPE_SECRET_KEY` | empty | Required when provider is `stripe` |
| `VELTRANE_STRIPE_WEBHOOK_SECRET` | empty | Required when provider is `stripe` |
| `VELTRANE_BILLING_WEBHOOK_TOLERANCE_SECONDS` | `300` | Reject older signatures |

## Bootstrap

| Variable | Default | Notes |
| --- | --- | --- |
| `VELTRANE_ADMIN_EMAIL` | `admin@veltrane.local` | Promoted to owner by `scripts/seed.py` |
| `VELTRANE_ADMIN_PASSWORD` | empty | If set, seed creates the account. Change it at first sign-in |

## Frontend

Set these in `frontend/.env.local` (gitignored) for local runs, or in the hosting provider's
environment for a deployment.

| Variable | Default | Notes |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | empty | Absolute API origin. Leave **empty** to call the API on the page's own origin and let Next rewrite `/api/*`. Public value, no secret |
| `VELTRANE_API_PROXY` | empty | Server-side rewrite target for `/api/:path*`, e.g. `http://127.0.0.1:12001`. Only read at build/start time |
| `VELTRANE_STATIC_EXPORT` | empty | Set to `1` to build a static site (`output: "export"`, `trailingSlash`, no rewrites/headers). Used by the Render Static Site build |

Same-origin is the recommended setup: the browser then never crosses origins, so there is no CORS
preflight and no second hostname to keep alive. `NEXT_PUBLIC_API_URL` is baked into the client
bundle at build time, so changing it requires a rebuild.

## Provider credentials

Exchange keys are **not** environment variables. They are entered per subscriber and encrypted at
rest. Only the platform-level KEK lives in the environment.

## Production checklist

`Settings` refuses to start when `VELTRANE_ENV=production` and any of these is wrong:

- `VELTRANE_SECRET_KEY` is the development placeholder or shorter than 32 characters
- `VELTRANE_COOKIE_SECURE` is not true
- `VELTRANE_BILLING_PROVIDER` is `mock`
- `VELTRANE_BILLING_PROVIDER` is `stripe` while either `VELTRANE_STRIPE_SECRET_KEY` or
  `VELTRANE_STRIPE_WEBHOOK_SECRET` is empty

Set the rest deliberately:

```bash
VELTRANE_ENV=production
VELTRANE_SECRET_KEY=<48+ random chars>
VELTRANE_MASTER_ENCRYPTION_KEY=<base64 of 32 bytes>
VELTRANE_COOKIE_SECURE=true
VELTRANE_REQUIRE_EMAIL_VERIFICATION=true
VELTRANE_LIVE_TRADING_ENABLED=false
VELTRANE_BILLING_PROVIDER=stripe   # or off while no processor is connected
VELTRANE_STRIPE_SECRET_KEY=sk_live_...
VELTRANE_STRIPE_WEBHOOK_SECRET=whsec_...
VELTRANE_CORS_ORIGINS=https://app.yourdomain.tld
VELTRANE_TRUSTED_PROXIES=*
```

The Render blueprint and the split-domain values used for `corvex.fun` are in
[DEPLOYMENT_RENDER.md](DEPLOYMENT_RENDER.md).

Never commit a `.env` file. `.env.example` holds placeholders only.
