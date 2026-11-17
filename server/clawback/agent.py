"""The agent's flows, one function per demo beat. api/index.py only parses requests and calls these.

  seed      read the three SLAs into memory (run once before the demo)
  ingest    read a pasted contract or email, pull out promises, remember it
  audit     fetch the status page, count downtime, work out what is owed
  draft     write the claim, using lessons recalled from memory
  reply     the vendor pushes back: remember it, run conflict review, show both facts
  resolve   a human picks the fact; the agent learns a lesson for this vendor
  paid      the credit landed: forget the claim so it is never claimed twice
  handoff   kill the agent; a new one rebuilds its picture from memory alone
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from . import sla
from .config import Settings, get_settings
from .llm import LLM
from . import agents as team
from .memory import AUDITOR, CLAIMS, INBOX, PLAYBOOK, PROMISES, WRITER, Memory, find_proposal
from .models import (
    AskRequest,
    AskResult,
    Audit,
    AuditRequest,
    Briefing,
    Claim,
    Conflict,
    ConflictFact,
    CreditRule,
    CreditTier,
    Health,
    IngestRequest,
    IngestResult,
    ReplyRequest,
    ResolveRequest,
    Source,
    VendorPromise,
)
from .statuspage import fetch_incidents
from .store import Store
from .vendors import all_vendors, get_vendor


class NotFound(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class Agent:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        self.store = Store(self.s)
        self.memory = Memory(self.s, self.store)
        self.llm = LLM(self.s)

    # ---------- reads ----------

    async def health(self) -> Health:
        return Health(
            ok=True,
            mode="demo" if self.s.demo_mode else "live",
            cognee=await self.memory.health(),  # type: ignore[arg-type]
            cognee_url=self.s.cognee_url if self.s.cognee_enabled else "",
            llm=self.llm.name,  # type: ignore[arg-type]
            store=self.store.kind,  # type: ignore[arg-type]
            status_pages="live" if self.s.live_status and not self.s.demo_mode else "snapshot",
            vendors=len(all_vendors()),
        )

    async def get_claim(self, claim_id: str) -> Claim:
        raw = await self.store.get(f"claim:{claim_id}")
        if not raw:
            raise NotFound(f"claim {claim_id}")
        return Claim.model_validate(raw)

    async def list_claims(self) -> list[Claim]:
        ids = await self.store.list("claims", 50)
        out = []
        for cid in ids:
            raw = await self.store.get(f"claim:{cid}")
            if raw:
                out.append(Claim.model_validate(raw))
        return out

    async def _save_claim(self, claim: Claim) -> Claim:
        claim.updated_at = _now()
        await self.store.set(f"claim:{claim.id}", claim.model_dump(mode="json", by_alias=True))
        return claim

    async def lessons(self, vendor_id: str) -> list[str]:
        return await self.store.get(f"lessons:{vendor_id}") or []

    # ---------- seed ----------

    async def seed(self) -> list:
        events = []
        for v in all_vendors():
            p = v.promise
            text = (
                f"Promise from {v.name} ({p.service}): {sla.rule_text(v)}. "
                f"The credit is a share of {p.fee_basis}. How to claim: {p.claim_how}. "
                f"Source: {p.source.title}, {p.source.url}. Status page: {v.status_page}."
            )
            _, ev = await self.memory.remember(text, title=f"{v.name} SLA", tags=[v.id, "promise"], dataset=PROMISES, agent=AUDITOR)
            events.append(ev)
        return events

    # ---------- ingest ----------

    async def ingest(self, req: IngestRequest) -> IngestResult:
        vendor = get_vendor(req.vendor_id)
        if not vendor:
            raise NotFound(f"vendor {req.vendor_id}")
        events = []
        _, ev = await self.memory.remember(req.text, title=req.title, tags=[vendor.id, req.kind], dataset=PROMISES, agent=AUDITOR)
        events.append(ev)
        found = await self.llm.extract_promises(vendor.name, req.text)
        promises: list[VendorPromise] = []
        for i, f in enumerate(found):
            tiers = [CreditTier(threshold=float(t.get("threshold", f["targetPct"])), inclusive=bool(t.get("inclusive", False)), credit_pct=float(t.get("creditPct", 10))) for t in f.get("tiers", [])]
            promises.append(
                VendorPromise(
                    id=f"{vendor.id}-email-{i}",
                    vendor_id=vendor.id,
                    service=f.get("service") or vendor.promise.service,
                    target_pct=float(f["targetPct"]),
                    window="quarter" if f.get("window") == "quarter" else "month",
                    rule=CreditRule(type="tiered", tiers=tiers or vendor.promise.rule.tiers),
                    fee_basis=f.get("feeBasis") or vendor.promise.fee_basis,
                    claim_deadline_days=int(f.get("claimDeadlineDays") or 30),
                    claim_how=f.get("claimHow") or vendor.promise.claim_how,
                    source=Source(title=req.title, quote=str(f.get("quote", ""))[:120], kind="email", date=req.date),
                    origin="email",
                    confidence=float(f.get("confidence", 0.8)),
                )
            )
        if promises:
            existing = await self.store.get(f"promises:{vendor.id}") or []
            await self.store.set(f"promises:{vendor.id}", existing + [p.model_dump(mode="json", by_alias=True) for p in promises])
        return IngestResult(vendor_id=vendor.id, promises=promises or [vendor.promise], memory=events)

    # ---------- audit ----------

    async def audit(self, req: AuditRequest) -> Audit:
        vendor = get_vendor(req.vendor_id)
        if not vendor:
            raise NotFound(f"vendor {req.vendor_id}")
        p = vendor.promise
        start, end = sla.window_bounds(p.window, req.window_start, period=req.period)
        live = self.s.live_status and not self.s.demo_mode
        incidents, source = await fetch_incidents(vendor, live=live)
        incidents = sla.classify(incidents, vendor, start, end, count_minor=req.count_minor)
        minutes = sla.window_minutes(start, end)
        by_comp = sla.downtime_by_component(incidents, vendor, start, end) if vendor.covered_components else {}
        worst = max(by_comp, key=by_comp.get) if by_comp and max(by_comp.values()) > 0 else ""
        # Per-service vendors are judged on their worst service; others on all counted downtime merged.
        down = by_comp[worst] if worst else sla.downtime_minutes(incidents, start, end)
        up = sla.uptime_pct(down, minutes)
        pct = sla.credit_pct(p.rule, up, down, minutes, req.affected_ratio)
        fee = sla.fee_in_window(req.monthly_fee_usd if req.monthly_fee_usd is not None else vendor.monthly_fee_usd, p.window)
        audit = Audit(
            id=_id("aud"),
            vendor_id=vendor.id,
            vendor_name=vendor.name,
            window=p.window,
            window_start=start,
            window_end=end,
            window_minutes=minutes,
            downtime_minutes=down,
            uptime_pct=up,
            target_pct=p.target_pct,
            breached=up < p.target_pct if p.rule.type == "tiered" else down > 0,
            credit_pct=pct,
            fee_in_window_usd=round(fee, 2),
            owed_usd=round(fee * pct / 100.0, 2),
            claim_by=end + timedelta(days=p.claim_deadline_days),
            rule_text=sla.rule_text(vendor),
            promise=p,
            incidents=[i for i in incidents if i.minutes_in_window > 0] or incidents[:12],
            status_source=source,
            in_progress=_now() < end,
            worst_component=worst,
            by_component=by_comp,
            computed_at=_now(),
        )
        await self.store.set(f"audit:{audit.id}", audit.model_dump(mode="json", by_alias=True))
        return audit

    # ---------- draft ----------

    async def draft(self, audit_id: str) -> Claim:
        raw = await self.store.get(f"audit:{audit_id}")
        if not raw:
            raise NotFound(f"audit {audit_id}")
        audit = Audit.model_validate(raw)
        session_id = f"claim-{audit.vendor_id}-{audit.window_start:%Y%m}-{uuid.uuid4().hex[:6]}"
        # What do we already know about claiming from this vendor? Memory first, then the app's own list.
        _, refs, _ = await self.memory.recall(
            f"What have we learned about claiming service credits from {audit.vendor_name}? How do they dispute claims?",
            datasets=[PLAYBOOK, PROMISES],
            agent=WRITER,
            # No session_id: a Cognee session binds to one dataset, and this claim's session belongs to clawback_claims.
            # Recalling with it against playbook/promises binds it there and the claim's own writes then get a 409.
        )
        lessons = await self.lessons(audit.vendor_id)
        email = await self.llm.draft_claim(audit, lessons)
        counted = [i for i in audit.incidents if i.counted]
        evidence = [audit.promise.source] + [Source(title=i.name, url=i.url, kind="status_page", date=i.started_at.date().isoformat(), quote=f"{i.minutes_in_window:g} min, {i.impact}") for i in counted[:8]]
        summary = (
            f"Open claim: {audit.vendor_name} owes {audit.owed_usd:,.2f} USD ({audit.credit_pct:g}% credit) for "
            f"{audit.window_start:%Y-%m-%d} to {audit.window_end:%Y-%m-%d}. Uptime {audit.uptime_pct:.3f}% vs promise "
            f"{audit.target_pct:g}%. {len(counted)} counted incidents, {audit.downtime_minutes:g} minutes. Claim by {audit.claim_by:%Y-%m-%d}."
        )
        ids, _ = await self.memory.remember(summary, title=f"Claim {audit.vendor_name} {audit.window_start:%b %Y}", tags=[audit.vendor_id, "claim"], dataset=CLAIMS, agent=WRITER)
        await self.memory.remember(f"Working on claim. {summary}", title="agent note", tags=[audit.vendor_id], dataset=CLAIMS, agent=WRITER, session_id=session_id)
        claim = Claim(
            id=_id("clm"),
            vendor_id=audit.vendor_id,
            audit=audit,
            status="draft",
            email=email,
            evidence=evidence,
            lessons=lessons,
            memory_data_ids=ids,
            session_id=session_id,
            created_at=_now(),
            updated_at=_now(),
        )
        qa, _ = await self.memory.entry(
            {"type": "qa", "question": f"How much does {audit.vendor_name} owe us?", "answer": summary, "context": audit.promise.source.title},
            dataset=CLAIMS, agent=WRITER, session_id=session_id, label=f"QA: how much does {audit.vendor_name} owe us?",
        )
        qa_id = qa.get("entry_id") or qa.get("entryId")
        if qa_id:
            await self.store.set(f"qa:{claim.id}", qa_id)
        await self.store.push("claims", claim.id)
        return await self._save_claim(claim)

    async def send(self, claim_id: str) -> Claim:
        claim = await self.get_claim(claim_id)
        claim.status = "sent"
        return await self._save_claim(claim)

    # ---------- reply: the vendor pushes back ----------

    async def reply(self, claim_id: str, req: ReplyRequest) -> Claim:
        claim = await self.get_claim(claim_id)
        audit = claim.audit
        read = await self.llm.read_reply(req.text)
        # The reply is filed in shared claims memory, where the Inbox Assistant can read it too.
        ids, _ = await self.memory.remember(req.text, title=f"{audit.vendor_name} reply to claim", tags=[audit.vendor_id, "vendor_reply"], dataset=CLAIMS, agent=WRITER)
        claim.memory_data_ids += ids
        await self.memory.improve(dataset=CLAIMS, agent=WRITER, review_conflicts=True)
        rows, _ = await self.memory.conflicts(dataset=CLAIMS, agent=WRITER)
        conflict = _from_cognee(rows, audit.vendor_name)
        if conflict is None:
            first = next((i for i in audit.incidents if i.counted), None)
            vendor_minutes = read.get("claimedDowntimeMinutes")
            conflict = Conflict(
                id=_id("cf"),
                question=f"How long was {audit.vendor_name} down in {audit.window_start:%B %Y}?",
                facts=[
                    ConflictFact(
                        id="status_page",
                        text=f"{audit.downtime_minutes:g} minutes across {sum(1 for i in audit.incidents if i.counted)} incidents on {audit.vendor_name}'s own status page",
                        source=Source(title=f"{audit.vendor_name} status page", url=first.url if first else "", kind="status_page"),
                    ),
                    ConflictFact(
                        id="vendor_reply",
                        text=(f"{vendor_minutes:g} minutes, per {req.sender}" if isinstance(vendor_minutes, (int, float)) else read.get("position", req.text[:160])),
                        source=Source(title=f"Reply from {req.sender}", quote=str(read.get("position", ""))[:120], kind="vendor_reply"),
                    ),
                ],
            )
        conflict.reason = str(read.get("lesson", ""))  # held until the human decides
        await self.store.set(f"reply:{claim.id}", read)
        claim.conflict = conflict
        claim.status = "contested"
        return await self._save_claim(claim)

    # ---------- resolve: the human decides, the agent learns ----------

    async def resolve(self, claim_id: str, req: ResolveRequest) -> Claim:
        claim = await self.get_claim(claim_id)
        if not claim.conflict:
            raise NotFound("no open conflict on this claim")
        c = claim.conflict
        if c.from_cognee:
            await self.memory.resolve(c.id, req.selected_fact_id, req.reason or "chosen in Clawback", dataset=CLAIMS, agent=WRITER)
        c.status, c.selected_fact_id = "resolved", req.selected_fact_id
        read = await self.store.get(f"reply:{claim.id}") or {}
        chosen = next((f for f in c.facts if f.id == req.selected_fact_id), None)
        if chosen is None:
            raise NotFound(f"fact {req.selected_fact_id}")
        sided_with_status_page = chosen.source.kind == "status_page" or "status page" in (chosen.text + " " + chosen.source.title).lower()
        lesson = str(read.get("lesson") or c.reason or "Attach status-page links with start and resolve times.")
        if read.get("countsOnly"):
            lesson += f" They only count: {read['countsOnly']}."
        lessons = await self.lessons(claim.vendor_id)
        if lesson not in lessons:
            lessons.append(lesson)
            await self.store.set(f"lessons:{claim.vendor_id}", lessons)
        # 1) The lesson goes into the playbook: shared with every Claims Writer, hidden from the Inbox Assistant.
        await self.memory.remember(f"Lesson for claiming from {claim.audit.vendor_name}: {lesson}", title=f"Lesson: {claim.audit.vendor_name}", tags=[claim.vendor_id, "lesson"], dataset=PLAYBOOK, agent=WRITER)
        # 2) Feedback on the agent's earlier answer, so improve() can reweight the graph.
        qa_id = await self.store.get(f"qa:{claim.id}")
        if qa_id:
            await self.memory.entry(
                {"type": "feedback", "qa_id": qa_id, "feedback_text": req.reason or "decided by a human", "feedback_score": 1 if sided_with_status_page else -1},
                dataset=CLAIMS, agent=WRITER, session_id=claim.session_id, label=f"feedback {'+1' if sided_with_status_page else '-1'} on the claim",
            )
        # 3) Score the claim-writer skill. A pushback means the first draft wasn't good enough, so Cognee
        #    proposes a rewrite of SKILL.md (apply=False: a human approves it in the UI).
        run, _ = await self.memory.entry(
            {"type": "skill_run", "selected_skill_id": team.SKILL_NAME, "task_text": f"Claim a service credit from {claim.audit.vendor_name}",
             "result_summary": f"Vendor pushed back: {read.get('position', '')}. Lesson: {lesson}", "success_score": 0.4, "feedback": -1.0},
            dataset=PLAYBOOK, agent=WRITER, session_id=None,  # the claim's session lives in clawback_claims; a session bound
            # to another dataset makes Cognee reject the entry (400 Invalid remember request). skill_run doesn't need one.
            skill_improvement={"skill_name": team.SKILL_NAME, "apply": False, "score_threshold": 0.9}, label="skill run scored 0.4 -> propose a rewrite",
        )
        proposal_id = find_proposal(run)
        if proposal_id:
            await self.store.set(f"proposal:{claim.id}", proposal_id)
        # 4) Distil this claim's session (notes, QA, feedback) into the permanent graph: self-improvement.
        await self.memory.improve(dataset=CLAIMS, agent=WRITER, session_ids=[claim.session_id], review_conflicts=False)
        claim.lessons = lessons
        if sided_with_status_page:
            claim.email = await self.llm.draft_claim(claim.audit, lessons)
            claim.email.subject = "Re: " + claim.email.subject
            claim.status = "sent"
        else:
            vendor_minutes = read.get("claimedDowntimeMinutes")
            if isinstance(vendor_minutes, (int, float)):
                a = claim.audit
                up = sla.uptime_pct(float(vendor_minutes), a.window_minutes)
                pct = sla.credit_pct(a.promise.rule, up, float(vendor_minutes), a.window_minutes)
                claim.audit = a.model_copy(update={"downtime_minutes": float(vendor_minutes), "uptime_pct": up, "credit_pct": pct, "owed_usd": round(a.fee_in_window_usd * pct / 100, 2)})
            claim.status = "accepted"
        claim.conflict = c
        return await self._save_claim(claim)

    # ---------- paid: forget ----------

    async def paid(self, claim_id: str) -> Claim:
        claim = await self.get_claim(claim_id)
        await self.memory.forget(claim.memory_data_ids, f"{claim.audit.vendor_name} credit paid", dataset=CLAIMS, agent=WRITER)
        await self.memory.remember(
            f"Settled: {claim.audit.vendor_name} paid the {claim.audit.owed_usd:,.2f} USD credit for {claim.audit.window_start:%B %Y}. Do not claim this period again.",
            title=f"Settled {claim.audit.vendor_name} {claim.audit.window_start:%b %Y}",
            tags=[claim.vendor_id, "settled"],
            dataset=CLAIMS,
            agent=WRITER,
        )
        claim.memory_data_ids = []
        claim.status = "paid"
        return await self._save_claim(claim)

    # ---------- ask + handoff ----------

    async def ask(self, req: AskRequest) -> AskResult:
        answer, refs, ev = await self.memory.recall(req.question, datasets=[PROMISES, CLAIMS, PLAYBOOK], agent=WRITER, session_id=req.session_id)
        return AskResult(answer=answer or "Nothing in memory about that yet.", references=refs, memory=[ev])

    async def handoff(self) -> Briefing:
        """A new agent with no state of its own: everything it says comes back from memory."""
        agent_id = _id("agent")
        a1, refs1, ev1 = await self.memory.recall("Which vendor credits are open or settled, how much is each, and when must we claim by?", datasets=[CLAIMS, PROMISES], agent=WRITER)
        a2, refs2, ev2 = await self.memory.recall("What lessons have we learned about how each vendor disputes credit claims?", datasets=[PLAYBOOK], agent=WRITER)
        open_claims = [r.title for r in refs1 if "claim" in r.title.lower()] or [line.strip("- ") for line in a1.splitlines() if "claim" in line.lower()][:5]
        lessons = [line.strip("- ") for line in a2.splitlines() if line.strip()][:5]
        return Briefing(
            agent_id=agent_id,
            recalled_from=self.memory.target,
            summary=a1 or "Memory is empty.",
            open_claims=open_claims,
            lessons=lessons,
            memory=[ev1, ev2],
        )

    # ---------- the Cognee track: agents, permissions, skill self-improvement ----------

    async def setup_agents(self) -> dict:
        return await team.setup(self.memory)

    async def permission_check(self) -> list[dict]:
        return await team.permission_check(self.memory)

    async def proposal(self, claim_id: str) -> dict:
        pid = await self.store.get(f"proposal:{claim_id}")
        if not pid:
            raise NotFound("no skill proposal for this claim yet")
        return await team.proposal(self.memory, pid)

    async def apply_proposal(self, claim_id: str) -> dict:
        """The human approved Cognee's rewrite of the claim-writer skill: record the run again with apply=True."""
        claim = await self.get_claim(claim_id)
        result, ev = await self.memory.entry(
            {"type": "skill_run", "selected_skill_id": team.SKILL_NAME, "task_text": f"Claim a service credit from {claim.audit.vendor_name}",
             "result_summary": "Human approved the proposed rewrite.", "success_score": 0.4, "feedback": -1.0},
            dataset=PLAYBOOK, agent=WRITER, session_id=None,  # the claim's session lives in clawback_claims; a session bound
            # to another dataset makes Cognee reject the entry (400 Invalid remember request). skill_run doesn't need one.
            skill_improvement={"skill_name": team.SKILL_NAME, "apply": True, "score_threshold": 0.9}, label="skill rewrite applied",
        )
        return {"ok": ev.ok, "result": result}

    async def reset(self, memory_too: bool = False) -> dict:
        await self.store.reset()
        if memory_too and self.memory.target == "cognee":
            for short in (PROMISES, CLAIMS, PLAYBOOK):
                try:
                    await self.memory.post("/api/v1/forget", json={"dataset": self.memory.ds(short)})
                except Exception:
                    pass
        return {"ok": True, "memoryCleared": memory_too}


def _from_cognee(rows: list[dict], vendor_name: str) -> Conflict | None:
    """Maps Cognee's FactConflict rows to our Conflict, keeping Cognee's ids so resolve goes back to it."""
    for row in rows or []:
        facts_raw = row.get("facts") or row.get("candidates") or []
        blob = str(row).lower()
        if vendor_name.lower() not in blob or len(facts_raw) < 2:
            continue
        facts = []
        for f in facts_raw[:4]:
            text = f.get("text") or f.get("statement") or f.get("value") or str(f)[:160]
            src = f.get("source") or f.get("evidence") or {}
            title = (src.get("name") or src.get("title")) if isinstance(src, dict) else str(src)[:60]
            facts.append(ConflictFact(id=str(f.get("id") or f.get("fact_id") or uuid.uuid4()), text=str(text)[:240], source=Source(title=title or "Cognee memory", kind="human")))
        return Conflict(id=str(row.get("id") or row.get("conflict_id")), question=str(row.get("question") or row.get("subject") or f"What is true about {vendor_name}?"), facts=facts, from_cognee=True)
    return None
