# Frontend + design: Nick

You own `app/`, `lib/` (frontend), `public/`, the design, the demo video and the README. Branch: `nick/frontend`.
`app/page.tsx` already runs the whole flow against the API (or the recorded replay). It's plumbing: split it into real screens and make it beautiful. Follow your hackathon-ui-playbook.

## How the data reaches you

- `lib/api.ts`: one function per endpoint. If the API is unreachable it **replays `data/demo/recorded.json` automatically**, so you can build every screen tonight without waiting on the backend. `NEXT_PUBLIC_DEMO=1` forces replay.
- `lib/types.ts`: every shape. Don't edit it alone; it mirrors Darian's `models.py`.
- Every screen has real data from real status pages (GitHub really did miss its promise this quarter).

## Visual thesis

**"A thermal receipt that prints what each vendor owes you."** Paper slips, dashed tear lines and monospace line items, with a pixel crab mascot (`app/_ui/Crab.tsx`, "Clawdia") that grabs the receipt when money is found. One accent: claw orange `--accent #FF6A1F`. Red only for contested and denied. Warm paper, warm ink, Instrument Serif for the big moments, Geist for UI, Geist Mono for numbers. Tokens are in `app/globals.css`.

## Screens (desktop first: judges watch a laptop; check 390px too)

| # | Screen | What's on it | Motion (only real events) |
|---|---|---|---|
| 1 | **Landing** | "you're owed." / grey "your vendors broke their promises." One giant accent pill: **Check my vendors**. The crab. Nothing else. | Crab idles; receipt paper curls behind |
| 2 | **Team** | 3 agent cards (Auditor, Claims Writer, Inbox Assistant) over 3 memory drawers (promises, claims, playbook). The permission grid from `api.permissions()`: ✓ / red ✕. | Each cell flips like a split-flap as the check runs; the denied cell shakes once |
| 3 | **Receipts** | One receipt per vendor (`Receipt.tsx`): counted incidents, downtime, uptime vs promise, the big serif **$630**. Twilio and Cloudflare print **$0**. | Receipts print line by line (`.print`); the amount counts up |
| 4 | **Claim** | Left: the email (subject, body). Right: evidence (SLA clause + incident links). Button: **Send**. | Email types in; Send dips to .92 |
| 5 | **Contested** | Vendor reply arrives. Two fact cards side by side (status page vs vendor), source on each. Tap one. "found by cognee" tag when `fromCognee`. | Red ring; cards drop in; the chosen card stamps |
| 6 | **Learned** | The lesson, plus the skill **before/after** (`api.proposal`) with an **Apply** button. The re-drafted email with the change highlighted. | Diff lines slide in |
| 7 | **Paid** | "paid." The claim tears off the receipt; the tape shows `forget`. Button: **Kill the agent** → the new agent's briefing from memory. | Tear-off clip-path; the crab hops |

**The memory tape (`MemoryTape.tsx`) stays visible on every screen** (right column on desktop, bottom drawer on phone). Each row shows the operation, **which agent**, the summary and the ms. Red rows are denials. This is the Cognee prize on screen; make it gorgeous.

## Order tonight

1. Import the repo to Vercel (Framework: Next.js). Every push to `nick/frontend` gets a preview URL.
2. Design canvas first (15–20 min): the 7 screens as artboards with a motion note each.
3. Build screens 1 → 3 → 4 → 5 → 7 → 2 → 6 (money path first, Cognee moments second).
4. Phone (390px) and desktop pass; main button above the fold.
5. Unslop pass (playbook "start without" list).
6. README as a product page: live link first, hero screenshot of the receipt, "What it does" table, Mermaid diagram (copy from docs/MVP.md), limits. Label fictional emails as fictional.
7. Optional: `/demo?auto` scripted player for the booth (template in your vault).

## Rules

- Never edit `api/` or `server/`. If you need a field, ask Darian (or add it to `lib/types.ts` together).
- Keep the replay fallback working: unplug the Wi-Fi and run the whole demo once before judging.
- No fake stats. Every number on screen comes from the API or the recorded real run.
