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
