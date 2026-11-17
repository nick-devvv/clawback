# API contract

Base path `/api/py`. JSON in and out, camelCase out (requests may use either case). Errors: `{"detail": {"code", "message"}}` with 404 or 422.
Live docs while the API runs: `http://localhost:3000/api/py/docs`. Types: `lib/types.ts` ⇄ `server/clawback/models.py`.

| Method | Path | Body | Returns | Cognee calls |
|---|---|---|---|---|
| GET | `/health` | | `Health` (cognee connected/unreachable/off, llm, store, statusPages) | — |
| GET | `/vendors` | | `Vendor[]` | — |
| POST | `/seed` | | `MemoryEvent[]` | `remember` × 3 (each vendor's SLA) |
| POST | `/ingest` | `{vendorId, kind: "sla"\|"email"\|"contract", title, text, date}` | `IngestResult {vendorId, promises, memory}` | `remember` |
| POST | `/audit` | `{vendorId, period?: "current"\|"last", monthlyFeeUsd?, affectedRatio?, countMinor?}` | `Audit` | — |
| POST | `/claims` | `{auditId}` | `Claim` (status `draft`) | `recall`, `remember` (graph + session), `remember/entry` QA |
| GET | `/claims` | | `Claim[]` | — |
| GET | `/claims/{id}` | | `Claim` | — |
| POST | `/claims/{id}/send` | | `Claim` (status `sent`; simulated) | — |
| POST | `/claims/{id}/reply` | `{text, sender}` | `Claim` (status `contested`, `conflict` filled) | `remember`, `improve(reviewConflicts)`, `conflicts` |
| POST | `/claims/{id}/resolve` | `{selectedFactId, reason}` | `Claim` (`sent` with a rebuttal if the status page wins, `accepted` with a new amount if the vendor wins; `lessons` grows) | `resolve`, `remember` lesson, feedback entry, `improve(sessionIds)` |
| POST | `/claims/{id}/paid` | | `Claim` (status `paid`, `memoryDataIds: []`) | `forget`, `remember` "settled" |
| POST | `/ask` | `{question, sessionId?}` | `AskResult {answer, references, memory}` | `recall` |
| POST | `/handoff` | | `Briefing {agentId, recalledFrom, summary, openClaims, lessons, memory}` | `recall` × 2 |
| GET | `/memory?limit=60` | | `MemoryEvent[]` newest first, for the memory tape | — |
| POST | `/agents/setup` | | `TeamReport {target, datasets, agents, grants, skill}` (run once) | datasets, agents/create, permissions, skills |
| GET | `/agents/permissions` | | `PermissionRow[] {agent, dataset, allowed, deniedBy, summary}`: 3 agents × 3 datasets | `recall` per agent (403 = denied; `deniedBy: "cognee"` only on a real 403) |
| GET | `/claims/{id}/proposal` | | Cognee's before/after rewrite of the claim-writer skill | `GET /api/v1/proposals/{id}` |
| POST | `/claims/{id}/proposal/apply` | | `{ok, result: {via, proposalId}}` | skill_run entry with `apply: true` + `proposal_id`; if Cognee rejects it, re-ingest the proposed procedure via `POST /api/v1/skills/` (`via: "reingest"`) |
| GET | `/inbox?vendor_id=github` | | `[{title, text, date, from}]` (Slashy when wired, samples otherwise) | — |
| POST | `/reset?memory=false` | | `{ok}` (wipes app state; `memory=true` also forgets the Cognee dataset) | `forget` |

## Key shapes (abridged; full fields in lib/types.ts)

```jsonc
// Audit
{
  "id": "aud_…", "vendorId": "github", "vendorName": "GitHub", "window": "quarter",
  "windowStart": "2026-10-01T00:00:00Z", "windowEnd": "2027-01-01T00:00:00Z",
  "downtimeMinutes": 1201.8, "uptimePct": 99.0928, "targetPct": 99.9, "breached": true,
  "creditPct": 10, "feeInWindowUsd": 6300, "owedUsd": 630, "claimBy": "2027-01-31T00:00:00Z",
  "ruleText": "99.9% uptime a quarter, or 10% back at or below 99.9%, 25% back below 99%",
  "worstComponent": "Actions", "byComponent": {"Actions": 1201.8, "Pull Requests": 927.6, "…": 0},
  "incidents": [{ "name": "…", "impact": "critical", "startedAt": "…", "minutesInWindow": 270, "url": "https://stspg.io/…", "counted": true, "reason": "critical outage on a covered service" }],
  "statusSource": "live | snapshot | none", "inProgress": true
}

// Claim.conflict, when the vendor pushes back
{
  "id": "cf_…", "question": "How long was GitHub down in October 2026?",
  "facts": [
    { "id": "status_page", "text": "1201.8 minutes across 15 incidents on GitHub's own status page", "source": { "kind": "status_page", "title": "GitHub status page", "url": "…" } },
    { "id": "vendor_reply", "text": "45 minutes, per GitHub Support", "source": { "kind": "vendor_reply", "title": "Reply from GitHub Support" } }
  ],
  "status": "unresolved", "fromCognee": false   // true when Cognee's own conflict review produced it (fact ids are then Cognee UUIDs)
}

// MemoryEvent (one row of the memory tape)
{ "id": "…", "at": "…", "op": "remember | recall | improve | forget | entry | conflicts | resolve", "target": "cognee | offline",
  "dataset": "clawback_claims", "sessionId": "claim-github-202610-ab12cd", "summary": "Claim GitHub Oct 2026 -> clawback_claims",
  "ms": 812, "ok": true, "detail": { "agent": "claims-writer" } }   // ok:false + "denied: …" = a permission refusal
```
