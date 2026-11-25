# Deployment

Target: a single small VM or a container platform with managed PostgreSQL and Redis. This is
deliberately boring infrastructure — one API process, one database, one cache. Scaling comes later,
when there is load to justify it.

## Topology

```
        ┌────────────┐        ┌──────────────────┐
Internet│  Reverse   │───────▶│  FastAPI (uvicorn,│──▶ PostgreSQL 17 (managed)
        │  proxy/TLS │        │  2 workers)      │──▶ Redis 7 (managed)
        └────────────┘        └──────────────────┘
                                      │
                                      └──▶ Exchange/broker APIs (outbound only)
```

No inbound connection from providers except signed webhooks. Exchanges are contacted outbound over
HTTPS; no ports are opened for them.

## Sizing for the first paying cohort

| Component | Minimum | Notes |
| --- | --- | --- |
| API | 1 vCPU / 1 GB | Two uvicorn workers, `--proxy-headers` |
| PostgreSQL | 1 vCPU / 1 GB, 20 GB disk | Managed, daily backups |
| Redis | 256 MB | Eviction policy `noeviction` — losing rate-limit keys is fine, losing them silently is not |

Cost estimate at list prices: roughly $25–45/month for the three components plus object storage for
backups. This is the realistic floor; a free tier will not keep a trading system with a database
and a cache running reliably.

## Build

```bash
cd backend
python3.13 -m venv .venv
.venv/bin/pip install --no-cache-dir -r requirements.txt
.venv/bin/alembic upgrade head
```

Container image (see `backend/Dockerfile`):

```bash
docker build -t veltrane-api:$(git rev-parse --short HEAD) backend
```

## Release procedure

1. CI green (lint, tests, dependency audit).
2. Take a database snapshot.
3. `alembic upgrade head` — migrations are additive; never drop a column in the same release that
   stops writing it.
4. Deploy the new image, rolling, one worker at a time.
5. Hit `/api/v1/health` and `/api/v1/ready` on the new instance.
6. Watch `order.rejected`, `webhook.invalid_signature` and 5xx rates for ten minutes.
7. Keep the previous image tagged for rollback.

Rollback is: deploy the previous image. If the release included a migration, roll forward with a
fix rather than downgrading in production.

## Health checks

- `GET /api/v1/health` — process alive, returns version and whether live trading is enabled.
- `GET /api/v1/ready` — checks database and Redis connectivity.
- `GET /api/v1/status/summary` — authenticated summary used by the app shell.

Point the platform's liveness probe at `/health` and its readiness probe at `/ready`.

## Reverse proxy

Terminate TLS at the proxy and forward `X-Forwarded-Proto`. Run uvicorn with
`--proxy-headers --forwarded-allow-ips=<proxy>`. The app sets HSTS in production. Set a request
body limit at the proxy (1 MB is generous for this API) and a 30-second upstream timeout, except for
backtest endpoints, which may need 120 seconds.

## Backups

- Nightly `pg_dump -Fc` to object storage, 30-day retention, encrypted at rest with a key the app
  does not hold.
- Weekly restore rehearsal: restore into a scratch database, run `alembic current`, then run the
  test suite against it. A backup that has never been restored is a hope, not a backup.
- Enable point-in-time recovery (WAL archiving) before onboarding paying subscribers. Without it the
  best-case data loss is 24 hours, which is unacceptable for trading records.
- Redis is treated as ephemeral. Losing it drops rate-limit counters and the revoked-token denylist;
  revoked access tokens then remain valid until they expire (≤ 15 minutes). Documented in
  SECURITY.md rather than papered over.

## Secrets

Inject environment variables from the platform's secret store. Do not bake them into the image, do
not write them to disk, do not put them in `docker-compose.yml` for production. Rotate the master
encryption key by adding a new `kek_version`, re-encrypting credential rows in a background job,
then retiring the old key.

## Logging and monitoring

- Structured JSON logs to stdout; the platform collects them.
- Every request carries `X-Request-ID` (echoed in the response) so a user report can be traced.
- Alert on: 5xx rate > 1 % for 5 minutes, `webhook.invalid_signature` > 0, `order.rejected` spike
  beyond the trailing baseline, readiness failures, database connection saturation, and any
  transition of `live_trading_enabled`.
- Alert immediately if the global kill switch is released unexpectedly.

## Incident response

1. Engage the global kill switch (`POST /admin/kill-switches/engage`, or set the file flag on the
   host if the API is unreachable).
2. Revoke affected sessions (`logout-all` per user, or rotate `VELTRANE_SECRET_KEY` to invalidate
   every token at once).
3. Preserve logs and the audit table before changing anything else.
4. Rotate the master encryption key if credentials may have been exposed, then require every
   subscriber to re-enter their keys.
5. Write a post-incident note with timeline, blast radius and the code or configuration change that
   prevents recurrence.

## Development and production separation

- Separate databases, separate Redis instances, separate secrets.
- `VELTRANE_ENV=production` disables `/docs`, enforces secure cookies, HSTS and a real billing
  provider.
- The demo market feed and the mock billing provider are available only outside production; the
  settings validator refuses to start otherwise.
