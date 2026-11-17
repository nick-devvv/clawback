# Backend: Darian

You own `api/`, `server/clawback/`, `data/`, `scripts/`, `tests/`, the Vercel env and Cognee. Branch: `darian/backend`.
The scaffold already runs the whole flow offline and passes `npm test`. Your job tonight is to make it run on **live Cognee and Claude**, then deploy it.

## Map

| File | What it does |
|---|---|
| `api/index.py` | FastAPI routes (the contract in `docs/API.md`). Thin: parse, call the agent, return. |
| `server/clawback/agent.py` | One function per demo beat: seed, ingest, audit, draft, reply, resolve, paid, handoff, plus agents/proposals |
| `server/clawback/memory.py` | **Every Cognee call.** REST + `X-Api-Key`, per-agent keys, the ACL, the memory tape log, the offline stand-in |
| `server/clawback/agents.py` | Cognee track setup: 3 datasets, 3 agents, grants, the claim-writer skill; permission check; skill proposals |
| `server/clawback/sla.py` | Downtime and credit math (pure, tested) |
| `server/clawback/statuspage.py` | Reads `{statusPage}/api/v2/incidents.json`, falls back to `data/status/` |
| `server/clawback/llm.py` | Claude: read email, read reply, write claim. Each has a fallback |
| `server/clawback/store.py` | Upstash Redis (or an in-process dict) for claims, audits and the tape |
| `server/clawback/inbox.py` | Slashy MCP stub (P2) |
| `data/vendors/*.json` | The 3 SLAs, checked against the source pages |

## Tonight, in order (each step has a check)

1. **Run it** (10 min). `npm install && python3 -m pip install -r requirements-dev.txt && npm test && npm run dev`. Open http://localhost:3000/api/py/docs.
   *Check:* `GET /api/py/health` → `mode: live`, `cognee: off`.
2. **Get Cognee** (20 min). Ask the Cognee team for a **Cognee Cloud URL + key**. Put them in `.env.local` as `COGNEE_URL` / `COGNEE_API_KEY` and export them for uvicorn (`set -a; source .env.local; set +a`).
   No Cloud? Self-host: `pip install cognee`, `export LLM_API_KEY=…`, `uvicorn cognee.api.client:app --port 8000`. On 401, `POST /api/v1/auth/login`, then `POST /api/v1/auth/api-keys`.
   *Check:* `health.cognee == "connected"`.
3. **Agents + permissions** (30 min). `curl -X POST localhost:8001/api/py/agents/setup`, then `curl localhost:8001/api/py/agents/permissions`.
   *Check:* 3 agents created and `inbox-assistant` × `clawback_playbook` → `allowed: false`, **and that refusal came from Cognee** (look for a 403 in the log). If agent keys don't get created (409 on a re-run means the key isn't shown again), delete the agents in Cognee or rename them in `agents.py`.
   Confirm the permission names (`read`, `write`, `delete`, `share`) and that an agent key reading a dataset it wasn't granted returns 403.
4. **Seed + audit + draft on live Cognee** (30 min). `POST /seed`, `POST /audit {vendorId:"github"}`, `POST /claims {auditId}`.
   *Check:* the memory tape (`GET /memory`) shows `remember` / `recall` with `target: cognee` and `ok: true`. Fix response parsing in `memory._read_recall` / `_find_ids` if the shapes differ (print the raw JSON once).
   Note: `remember` builds the graph (it can take a few seconds). Seed before the demo, not during it.
5. **Self-improvement loop** (45 min). `POST /claims/{id}/reply` with `data/emails/github-pushback.txt`, then `POST /claims/{id}/resolve {selectedFactId}`, then `GET /claims/{id}/proposal`, then `POST …/proposal/apply`.
   *Check:* the tape shows `improve` (conflict review), `conflicts`, `entry` (feedback + skill run), `improve` (session distil). If Cognee's conflict review returns a FactConflict, the card says "found by cognee" (`fromCognee: true`); otherwise our two-source conflict is used. Either is fine for the demo.
   If no proposal id comes back, lower `score_threshold` or raise it above the score (a proposal is only made when the score is **below** the threshold). Confirm with the Cognee team how `apply: true` behaves over REST.
6. **Claude** (10 min). `ANTHROPIC_API_KEY` set → `health.llm == "claude"`. Claim emails get better; the template still works without it.
7. **Snapshot + record** (10 min, at about 7:30). `npm run snapshot` (fresh status feeds), then `npm run record` (with the API running) → `data/demo/recorded.json` now holds a **live** run. Commit both.
8. **Deploy** (20 min). Vercel env: `COGNEE_URL`, `COGNEE_API_KEY`, `ANTHROPIC_API_KEY`, Upstash (Marketplace → KV_*). Agent keys live in Redis after setup, so run `POST https://<app>.vercel.app/api/py/agents/setup` once **on the deployed app**.
   *Check:* the full flow works on the Vercel URL. If the Python function fights you, deploy the API anywhere (`uvicorn api.index:app`) and set `NEXT_PUBLIC_API_BASE` for Nick.

## Rules

- Change a response field? Update `server/clawback/models.py` **and** `lib/types.ts` and tell Nick.
- Never put keys in code or commit `.env.local`.
- Small PRs into `main`, with `npm test` green.
- Whatever breaks, keep the fallback paths: offline memory, snapshots, templates. They are why the demo can't die.

## If you finish early (P2)

- Slashy: get the MCP URL + token from the Slashy team, implement `inbox.vendor_emails` and `inbox.create_draft` (`tools/list`, then `tools/call`), and call `create_draft` from `agent.draft`.
- Add a 4th vendor: copy `data/vendors/twilio.json`, point `statusPage` at any Atlassian Statuspage, and copy the SLA terms from its published page.
