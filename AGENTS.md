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
.venv/bin/python -m pytest               # 151 tests, needs Postgres + Redis
VELTRANE_DATABASE_URL=... .venv/bin/alembic upgrade head

# frontend
cd frontend
npm run lint        # eslint .  (next lint is deprecated in 15.5)
npm run typecheck   # tsc --noEmit
npm run test        # vitest run (node env, pure logic; config: vitest.config.ts)
npm run build
```

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

## Two failure modes worth remembering

- **Float boundaries in risk rules.** `stake / price * price` does not round-trip. Round notional
  before comparing it to a limit (`_notional` in `app/risk/rules.py`), or a $10 stake fails the
  $10 minimum intermittently depending on the price the feed happens to serve.
- **Duplicates are terms, not symbols.** Two entries on the same underlying with different stakes
  are different orders. Matching on symbol and side alone locks a user out of their own account for
  the length of the window, and it hides real trades from the risk engine.
