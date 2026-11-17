# The demo (90 seconds)

**Setup before judges arrive:** `POST /api/py/agents/setup`, `POST /api/py/seed`, a fresh `npm run snapshot`. Open the app full screen with the memory tape visible.

| Time | Say | Click | Judges see |
|---|---|---|---|
| 0:00 | "Startups pay for dozens of tools. Every one promised uptime, and when they miss, you're owed money. Nobody claims it." | — | Landing: *you're owed.* |
| 0:10 | "Clawback is three agents sharing one Cognee memory, with permissions. The inbox agent talks to vendors, so it can't see our negotiation playbook." | **Agents + permissions** | Grid fills; inbox × playbook goes red: *denied by Cognee* |
| 0:22 | "The auditor reads each vendor's SLA and their own status page." | **Check my vendors** | Receipts print. GitHub: **$630**, Actions down 1,202 min this quarter. Twilio, Cloudflare: $0. "It doesn't cry wolf." |
| 0:35 | "The claims writer recalls what we've learned and writes the claim, citing their own clause and incident links." | **Claim** → **Send** | The email, with evidence |
| 0:45 | "GitHub pushes back: only 45 minutes count." | **Vendor pushes back** | Contested card: status page vs vendor, both with sources; `improve` + `conflicts` on the tape |
| 0:55 | "I side with their own status page. Now watch it learn." | tap the status-page fact | Lesson stored in the playbook; feedback; skill scored; `improve` distils the session; skill before/after → **Apply** |
| 1:08 | "Credit paid. It forgets the claim so it never asks twice." | **Mark paid** | `forget` on the tape |
| 1:15 | "And if the agent dies?" | **Kill the agent** | A new agent's briefing, recalled from memory alone, lessons included |
| 1:25 | "Clawback: you're owed. We go get it." | — | Crab with the receipt |

## Judge questions

- **Is the downtime number right?** It's the vendor's own public status page, counting only major and critical incidents on covered services, with overlaps merged. Vendors measure with internal monitoring, so this is the claim we file, with evidence, not a verdict.
- **Why Cognee and not a database?** The value is in what changes: contradictions between sources, lessons that rewrite the agent's skill, memory shared across agents with real permissions, and forgetting. That's `improve`, agents + permissions, and `forget`, not CRUD.
- **Business model?** Contingency: 20% of recovered credits, plus a seat price for monitoring. Every SaaS-heavy startup is a customer.
- **What's real?** Status data, SLA terms (linked) and the math are real. The vendor reply is a written sample, and it says so.
