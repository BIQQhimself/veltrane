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
