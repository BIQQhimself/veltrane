# AGENTS.md

Repository notes for automated agents working on VELTRANE.

## Layout

- `backend/` — FastAPI + SQLAlchemy + Alembic (Python 3.13). `app/` is the package, `tests/` the suite.
- `frontend/` — Next.js 15.5 App Router, TypeScript, Tailwind, ESLint 9 flat config.
- `docs/` — long-form design and policy documents; top-level `*.md` files are the deliverables
  named in the build instruction.

## Commands

```bash
# backend
cd backend
.venv/bin/pip install -r requirements.txt
.venv/bin/ruff check app tests           # config lives in backend/pyproject.toml
.venv/bin/python -m pytest               # ~385 tests, needs Postgres + Redis
VELTRANE_DATABASE_URL=... .venv/bin/alembic upgrade head

# frontend
cd frontend
npm run lint        # eslint .  (next lint is deprecated in 15.5)
npm run typecheck   # tsc --noEmit
npm run test        # vitest run (node env, pure logic; config: vitest.config.ts)
npm run build
```

## Product rules that are easy to break

- **One minute is the minimum expiry on every path.** `TradingRule` in `app/db/constants.py` is the
  only definition. The catalogue (`services/contract_catalogue.tradeable_terms`), the Deriv request
  schemas (`api/v1/deriv.py`), the execution layer (`trading/deriv_execution._assert_duration_floor`)
  and the automation runner (`services/autotrade._halt_reason`) all apply it, and
  `tests/test_duration_floor.py` pins each of them. Deriv prices 15-second and tick contracts;
  refusing them is a product decision, not a venue limitation.
- **Plan codes come from `PlanCode`** (`free`, `basic`, `pro`, `elite`, `vip`). Do not write a
  `Literal[...]` list of plans in a schema or a component: `api/schemas.py` validates against
  `PlanCode.ALL`, and the frontend reads `TIERS`/`TIER_ORDER` from `src/lib/membership.ts`.
- **The daily allowance covers real money too.** `demo_executions` and `live_executions` are
  separate counters compared with the same plan limit by `demo_execution_limit` and
  `live_execution_limit` in `app/risk/rules.py`. A new execution path must increment the right
  counter after a confirmed fill.
- **Brand versus hostname.** The brand is VELTRANE; `corvex.fun` is the legacy deployment hostname
  and still appears in `render.yaml`, CI and the deployment notes because that is what resolves.
  Do not "fix" those hostnames to a domain that has not been cleared.

## CI expectations

`.github/workflows/ci.yml` runs backend (ruff, pip-audit --strict, alembic upgrade head, pytest) and
frontend (eslint, tsc, vitest, next build). Reproduce a job locally before pushing:

- Lint with the pinned tool: `pip install ruff==0.17.6 && ruff check app tests`.
- Audit with `pip install pip-audit==2.10.1 && pip-audit -r requirements.txt --strict`. Pinned
  versions must stay free of advisories; upgrade the dependency rather than skipping the check.
- Tests must pass under the plain `pytest` console script, not only `python -m pytest` — that is
  why `backend/pytest.ini` sets `pythonpath = .`.
- Run `next build` only when the dev server is stopped: a build overwrites `.next/` and breaks a
  running `next dev`. Restart the dev server on its assigned port afterwards.

## Conventions that matter here

- Never enable live trading, never weaken a risk control, never relax a test assertion to make CI
  green.
- Credentials are encrypted at rest and never returned by an API response. `docs/SECURITY.md` and
  `docs/THREAT_MODEL.md` are the reference for what may be exposed.
- Ruff's rule set is deliberately narrow (E4/E7/E9/F/I/UP/B). Do not add broad `ignore` lists; if a
  rule is genuinely wrong for FastAPI patterns, extend `extend-immutable-calls` instead.
- Paper and demo data must stay labelled as simulated in API responses and UI.

## Session notes (Nov 2026 — Phase 2 product pass)

- `app/services/market_data.py::price_at(symbol, when, timeframe)` returns the price at an exact
  instant by interpolating the deterministic candle series. Binary settlement prices at the contract
  expiry, not at "now", so a restarted or late worker cannot reprice a contract.
- Demo history lives in `backend/scripts/seed_demo.py` (idempotent: `_reset()` drops the demo
  user/org first). Entry price = open of the bar at start, exit = close of the bar at expiry, so
  stored P&L is reproducible from the feed. Re-run after changing the feed maths.
- `/portfolio/performance` seeds the equity curve with `settings.paper_starting_balance`; drawdown
  is peak-to-trough on *equity*, not on cumulative P&L (a P&L-based peak goes negative and produced
  a nonsense 85% figure).
- Price formatting: use `price()` from `src/lib/format.ts` (≈5 significant digits, min 2 dp). The
  chart picks axis decimals from the instrument tick, not the zoom span, and hides any rail label
  that would sit under the live-price chip.
- `Table` in `src/components/ui/table.tsx` must not impose a min-width: half-width panels clipped
  their rightmost column. Cells are `px-3 sm:px-4` so four-column tables fit a 390 px viewport.
- Allocations on `/app/portfolio` include unallocated cash as a slice; percentages are of account
  equity, never of position value alone.

## Session notes (Nov 2026 — trade traceability)

- A binary contract has no `orders` row, so its risk decision was unreachable from the trade record.
  `binary_contracts.trade_id` (migration `9b2e5c7a41d0`) is set when settlement writes the trade, and
  `serializers.trade_detail` falls back to that contract's decision, returning it as a top-level
  `risk_decision` (the drawer reads `data.risk_decision ?? data.order.risk_decision`).
- Seeded demo history is written straight to the ledger, so those rows carry no decision. The drawer
  says so in plain words rather than showing an empty tab; do not fabricate decisions for them.

## Session notes (Nov 2026 — autonomous paper runner, chart depth, risk budget)

- `app/services/scheduler.py` is a daemon thread started from the FastAPI lifespan. It ticks every
  `running` paper session once per `VELTRANE_SCHEDULER_INTERVAL_SECONDS`. It is paper-only: it calls
  the same tick path as `POST /paper-sessions/{id}/tick`, which never reaches a live adapter. Run it
  on exactly one replica; it is not a distributed lock. State is in `/admin/system/health` as
  `paper_scheduler`.
- `trading_engine.risk_budget(db, user)` (exposed at `GET /trading/risk-budget`) mirrors the blocking
  rules' arithmetic for display. It must stay read-only — it returns numbers, never an approval. If
  you change a rule's maths in `app/risk/rules.py`, change `risk_budget` in the same commit;
  `tests/test_risk_budget.py` pins the daily-loss case at 3% of equity.
- RSI on a flat window is neutral (50), not 100: both average gain and average loss are zero, so
  `rsiFrom()` special-cases it. Any other value makes a doji-heavy chart look overbought.
- The candle chart's time axis switches from clock times to dates once the visible span exceeds a
  day; keep `axisTicks`/`tickLabel` in `charts/candles.tsx` as the single source for that decision.
- Review accounts come from `backend/scripts/seed_testers.py` (idempotent, resets the password hash).
  Use a routable domain — `.local`, `.test`, `.example` and `.invalid` are rejected by the login
  validator, so an account seeded on those domains can never sign in. `REVIEW_ACCESS.md` is the
  reviewer-facing brief; keep it in step with the script's SPECS list.

## Session notes (Nov 2026 — durations come from the venue, three paid tiers)

- **Never hardcode a duration menu.** `app/services/contract_catalogue.py` reads Deriv's
  `contracts_for`, walks the ladder inside each published band and keeps only terms the proposal
  engine prices. `GET /deriv/contracts?symbol=...` serves it; `deriv_execution._assert_offered`
  enforces it on preview *and* submit, including the autonomous runner. The terminal renders only
  what that endpoint returned (`venueTermOptions`/`groupTerms` in `src/lib/deriv.ts`).
- **A tick term has no `duration_seconds`.** `None` is deliberate; converting ticks to seconds
  would invent a number and break settlement, the duplicate window and the audit trail.
- **A missing expiry price voids the contract** and returns the stake. Repricing at "now" would
  fabricate a result in a subscriber's history.
- **Payout sanity band is 1–98 %**, not 95 %: Deriv's own ceiling sits near 95.6 %, so a tighter
  bound refused legitimate contracts. The band is an implausibility guard, not a venue rule.
- **Plans are Free (sandbox) / Basic $19 / Pro $49 / Elite $149.** All three paid tiers are
  live-*eligible*; authorisation, the platform switch, the checklist and the risk engine still
  gate every live order. `SUBSCRIPTIONS.md` is the source of truth.
- **Free tier still exists** as a read-only sandbox (5 demo executions/day) — it is what
  `seed_testers.py` and the acceptance tests use.
- Backend `355 passed`; frontend `63 passed`; `VELTRANE_STATIC_EXPORT=1 npm run build` exports
  cleanly. Rebuild `out/` after touching `page.tsx` or the deployed palette goes stale.

## Runtime topology in this sandbox (learned the hard way)

- **The API must listen on `0.0.0.0:12001`.** Port 12001 is the only port the platform's reverse
  proxy forwards to `work-2-<id>.prod-runtime.all-hands.dev`. A uvicorn bound to `127.0.0.1:8000`
  looks healthy inside the container but the public host answers `502 Bad Gateway`.
- **Run exactly one API process.** The paper scheduler is an in-process thread, so two uvicorn
  workers would tick the same sessions twice and double the simulated trades.
- **Frontend (port 12000 → `work-1-...`) uses the same-origin proxy.** `frontend/.env.local` keeps
  `NEXT_PUBLIC_API_URL=` empty and sets `VELTRANE_API_PROXY=http://127.0.0.1:12001`, so browser
  calls go to `/api/*` on the page's own host. Reviewers then only need one URL, and
  `https://work-1-.../api/v1/health` returns JSON.
- **Restarting the dev server:** stop `next-server` first, then `rm -rf .next`, then `npx next dev`.
  Deleting `.next` under a live server leaves it serving `500` on every route with
  `ENOENT ... routes-manifest.json`.
- After `npm run build`, the dev server must be restarted the same way; the two share `.next`.

## Deriv wiring on the review instance

- The API talks to `backend/scripts/deriv_sandbox.py` on `127.0.0.1:12003`, not to
  `api.derivws.com`. Restart it with
  `VELTRANE_DERIV_REST_BASE=http://127.0.0.1:12003`,
  `VELTRANE_DERIV_PUBLIC_WS_URL=ws://127.0.0.1:12003/trading/v1/options/ws/public` and
  `VELTRANE_DERIV_SANDBOX=true` in the environment. Forgetting those three makes every venue call
  hit the real gateway and come back `401`, which looks like a broken PAT.
- The sandbox accepts one PAT (`pat_test_token_0123456789abcdef`, app id `12345`) and two accounts:
  `VRTC900001` (demo) and `CR700001`. Any other `account_id` fails verification, correctly.
- `uvicorn` does not reload here. After changing API code, kill the PID and start it again with the
  three variables above; otherwise you are testing the old process.
- `/auth/login` is rate limited per address. Probe scripts must back off on `429` (about 15 s) or
  everything after the first few calls fails for the wrong reason.
- Seed scripts place contracts through the public API, so they obey the same rules a user does,
  including the 60-second contract floor. A seed payload under a minute is refused with
  `min_duration` and leaves the account with no history.

## Page titles and the auth boundary

- Route metadata (`export const metadata`) only reaches the tab on a full document load. Client-side
  navigation between `/login` and `/app` leaves the previous title in place, so signing in, signing
  out and the gate's expired-session redirect all use `window.location`, not `router.push`.

## Two failure modes worth remembering

- **Float boundaries in risk rules.** `stake / price * price` does not round-trip. Round notional
  before comparing it to a limit (`_notional` in `app/risk/rules.py`), or a $10 stake fails the
  $10 minimum intermittently depending on the price the feed happens to serve.
- **Duplicates are terms, not symbols.** Two entries on the same underlying with different stakes
  are different orders. Matching on symbol and side alone locks a user out of their own account for
  the length of the window, and it hides real trades from the risk engine.

- Seed Deriv demo history (sandbox gateway): `VELTRANE_TESTER_PASSWORD=... python -m scripts.seed_deriv_history --email elite@veltrane.dev`

## Render deployment (free tier)

- `render.yaml` is the Blueprint: `veltrane-api` (Python web service, `rootDir: backend`),
  `veltrane-web` (Render *static site* from `frontend/out`), `veltrane-db` (free Postgres).
  `DEPLOYMENT_RENDER.md` holds the DNS/cookie/CORS/deploy notes for the legacy `corvex.fun`
  hostname (see "Brand versus hostname" above).
- The static build requires `VELTRANE_STATIC_EXPORT=1` (`next.config.ts` then sets
  `output: "export"`, `trailingSlash`, and drops rewrites/headers, which a static host cannot
  honour). Build it locally with
  `VELTRANE_STATIC_EXPORT=1 NEXT_PUBLIC_API_URL=https://api.corvex.fun npm run build` and check
  `frontend/out/<route>/index.html` exists.
- Static export forbids server-side `searchParams`; `/verify` therefore reads the token from
  `window.location.search` in the client form. Keep new pages client-side if they need query data.
- Production forces `VELTRANE_BILLING_PROVIDER` away from `mock`. With no processor connected use
  `off`: checkout and billing webhooks answer `503 billing_disabled` instead of granting plans.
- On Render every request arrives through the platform proxy, so `VELTRANE_TRUSTED_PROXIES=*`
  (plus uvicorn `--proxy-headers`) is correct there. Without it, all visitors share one rate-limit
  bucket. The matcher accepts exact IPs, CIDR blocks and `*` (`Settings.is_trusted_proxy`).
- Live execution needs two keys: `VELTRANE_LIVE_TRADING_ENABLED` (operator) and the staff key in
  `system_settings['live_trading.staff_control']` (`app/services/platform_switch.py`,
  `PUT /api/v1/admin/live-trading`). Read the effective state with `platform_switch.effective(db)`,
  never `settings.live_trading_enabled`, inside request paths that gate execution.
- The frontend API client retries `502/503/504` and network errors twice (~2.5 s, ~7 s) because
  free instances sleep; do not remove that without giving the user a cold-start message.
- Local sandbox note: this environment has no Docker. Postgres/Redis come from apt
  (`sudo pg_ctlcluster 17 main start`, `redis-server --daemonize yes`) and the `veltrane` role
  password must match `.env` (`VELTRANE_DATABASE_URL`). The test suite also needs `veltrane_test`.

## Email, referrals and Deriv OAuth

- One category list decides mail routing: `email_service.IMMEDIATE_CATEGORIES`. `notifications.EMAIL_CATEGORIES`
  aliases it, so a new category is added once. Trade and order categories never mail individually —
  they belong to the daily digest.
- `email_allowed()` returns `True` for `MANDATORY_CATEGORIES` (`security`, `billing`) before it reads
  preferences. Don't "simplify" that away: security notices must survive a user switching everything off.
- Mail rows only get `sent_at` after the provider returns 2xx. A test that asserts delivery must set
  `VELTRANE_EMAIL_PROVIDER=resend` and stub the HTTP call, or assert the outbox state instead.
- Referral links must be HTTPS **and** carry a tracking parameter (`t`, `affiliate_token`, `sidi`,
  `ca`); `referrals.update_link` raises otherwise, and the admin route maps that to `400`.
- Commission is never computed from clicks. `referrals.record_conversion` is the only path, and it
  is staff-only by design (`404` for subscribers, not `403`).
- Deriv OAuth stores only the SHA-256 of the state value plus a short-lived PKCE verifier
  (`deriv_oauth_states`). Deriv issues no refresh token: an expired token is a "reconnect" state,
  not something to retry in a background job.
- A Deriv authorisation maps to exactly one `connections` row; switching between demo and live
  reuses it. Creating a second connection for the same Deriv account is a bug, and
  `test_deriv_oauth.py` asserts against it.
- Admin email campaigns are stored in `email_campaigns` and fanned out by
  `email_service.send_due_campaigns`; the scheduler calls it, so a campaign marked `scheduled`
  sends even if the operator closes the browser. Promotional campaigns respect
  `promotional_allowed()`; transactional mail does not.
- Never run `next build` while `next dev` is serving the same `frontend/.next`. The build
  overwrites the dev server's chunks and every route then renders as an unstyled skeleton with
  no hydration ("Cannot find module '/NNN.js'"). Stop the dev server, run the build, then
  `rm -rf .next` and restart dev. `npm run build` is safe in CI, where nothing else holds `.next`.
- The secondary palette token is the brand champagne, not a second blue: the legacy `champagne`
  Tailwind key aliases `--vt-secondary-*`, so `<Button variant="primary">` and every `champagne-*`
  utility follow whatever is stored under `ui.theme`. Republish from `/admin/appearance` on a
  deployment whose stored palette predates a change to `services/theme.py`.
