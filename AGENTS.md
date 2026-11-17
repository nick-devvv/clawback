# Rules for coding agents (and humans)

Clawback: an agent that remembers every promise your vendors made, checks it against their own status page,
and claims the credit you're owed. Spec: `docs/MVP.md`. Contract: `docs/API.md`.

## Ownership (do not cross without asking)

- **Nick (frontend + design), branch `nick/frontend`:** `app/`, `lib/`, `public/`, `README.md` visuals.
- **Darian (backend), branch `darian/backend`:** `api/`, `server/`, `data/`, `scripts/`, `tests/`, `vercel.json`, `requirements*.txt`.
- Shared, change together in one PR: `lib/types.ts` ⇄ `server/clawback/models.py`, `docs/API.md`.

## Build and test

- `npm run dev`: Next on :3000, FastAPI on :8001 (`/api/py/*` is rewritten to it). API docs: http://localhost:3000/api/py/docs
- `npm test`: Python tests (SLA math + full flow offline). Keep green before merging.
- `npm run build`: must pass before merging to `main` (Vercel deploys `main`).

## Conventions

- Every external call has a fallback (snapshots, offline memory, templates, recorded replay). Don't remove them.
- All Cognee calls go through `server/clawback/memory.py` so they appear on the memory tape.
- No secrets in code. Env vars are listed in `.env.example`.
- This is Next.js 16: read `node_modules/next/dist/docs/` before using an API you're unsure of.
- UI copy: one headline per screen, no helper paragraphs, no fake numbers.
