"""Cognee is Clawback's memory. Every call goes through this file and lands in the memory log
(the UI's "memory tape"), tagged with which agent made it, so judges can watch it happen.

What the Cognee track asks for, and where it lives:
  Self-improvement   improve() after every outcome: conflict review, feedback weights, and distilling the
                     claim's session into the permanent graph. Plus the claim-writer SKILL.md that Cognee
                     rewrites from scored runs (skill_run entry -> proposal -> apply). See agent.resolve().
  Shared memory      three agents (Auditor, Claims Writer, Inbox Assistant), each a Cognee agent user with
  across agents      its own API key, reading and writing the same datasets. See agents.py.
  Permissions        three datasets with different grants: promises (everyone reads), claims (inbox can
                     read), playbook (inbox can't). A denied read shows up red on the tape.

Datasets:
  clawback_promises   SLA promises and status-page evidence      Auditor writes · all read
  clawback_claims     claims, vendor replies, settlements         Claims Writer writes · Inbox reads
  clawback_playbook   lessons learned + the claim-writer skill    Claims Writer only

REST with httpx (X-Api-Key), the same endpoints cognee.serve() uses, so the Vercel function stays tiny.
With no COGNEE_URL an offline stand-in runs the same rules (including the permission table) and every
event says "offline".
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import Settings
from .models import MemoryEvent, MemoryTarget, Source
from .store import Store

LOG_KEY = "memlog"
OFFLINE_KEY = "offline_memory"
AGENT_KEYS = "agent_keys"

PROMISES, CLAIMS, PLAYBOOK = "promises", "claims", "playbook"
AUDITOR, WRITER, INBOX, OWNER = "auditor", "claims-writer", "inbox-assistant", "owner"

# Who may do what. Mirrored into Cognee as dataset grants by agents.setup(); enforced locally when offline.
ACL: dict[str, dict[str, set[str]]] = {
    AUDITOR: {PROMISES: {"read", "write"}, CLAIMS: set(), PLAYBOOK: set()},
    WRITER: {PROMISES: {"read"}, CLAIMS: {"read", "write", "delete"}, PLAYBOOK: {"read", "write"}},
    INBOX: {PROMISES: {"read"}, CLAIMS: {"read"}, PLAYBOOK: set()},
    OWNER: {PROMISES: {"read", "write", "delete"}, CLAIMS: {"read", "write", "delete"}, PLAYBOOK: {"read", "write", "delete"}},
}


class Denied(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9.%]+", text.lower()) if len(w) > 2}


class Memory:
    def __init__(self, settings: Settings, store: Store):
        self.s = settings
        self.store = store
        self.target: MemoryTarget = "cognee" if settings.cognee_enabled else "offline"
        self.prefix = settings.cognee_dataset  # "clawback" -> clawback_promises, ...
        self._ids: dict[str, str] = {}

    def ds(self, short: str) -> str:
        return f"{self.prefix}_{short}"

    # ---------- plumbing ----------

    async def _key(self, agent: str) -> str:
        """Each agent calls Cognee with its own key (created by agents.setup); the owner key otherwise."""
        if agent != OWNER:
            keys = await self.store.get(AGENT_KEYS) or {}
            if keys.get(agent, {}).get("key"):
                return keys[agent]["key"]
        return self.s.cognee_api_key

    async def _headers(self, agent: str) -> dict[str, str]:
        key = await self._key(agent)
        return {"X-Api-Key": key} if key else {}

    async def _log(self, op: str, summary: str, started: float, ok: bool, *, agent: str, dataset: str = "", session_id: str | None = None, detail: dict | None = None) -> MemoryEvent:
        event = MemoryEvent(
            id=uuid.uuid4().hex[:12],
            at=_now(),
            op=op,  # type: ignore[arg-type]
            target=self.target,
            dataset=dataset,
            session_id=session_id,
            summary=summary,
            ms=int((time.perf_counter() - started) * 1000),
            ok=ok,
            detail={"agent": agent, **(detail or {})},
        )
        await self.store.push(LOG_KEY, event.model_dump(mode="json", by_alias=True))
        return event

    async def log(self, limit: int = 60) -> list[MemoryEvent]:
        return [MemoryEvent.model_validate(e) for e in await self.store.list(LOG_KEY, limit)]

    async def post(self, path: str, *, agent: str = OWNER, json: Any = None, data: Any = None, files: Any = None, params: dict | None = None, timeout: float = 120.0) -> Any:
        async with httpx.AsyncClient(timeout=timeout, headers=await self._headers(agent)) as client:
            resp = await client.post(f"{self.s.cognee_url}{path}", json=json, data=data, files=files, params=params)
            if resp.status_code == 403:
                raise Denied(resp.text[:200])
            if resp.status_code >= 400:
                raise RuntimeError(f"{path} -> {resp.status_code}: {resp.text[:300]}")
            return resp.json()

    async def get(self, path: str, *, agent: str = OWNER, params: dict | None = None, timeout: float = 30.0) -> Any:
        async with httpx.AsyncClient(timeout=timeout, headers=await self._headers(agent)) as client:
            resp = await client.get(f"{self.s.cognee_url}{path}", params=params)
            if resp.status_code == 403:
                raise Denied(resp.text[:200])
            if resp.status_code >= 400:
                raise RuntimeError(f"{path} -> {resp.status_code}: {resp.text[:300]}")
            return resp.json()

    def _check(self, agent: str, short: str, perm: str) -> None:
        """Offline mode enforces the same table Cognee enforces online."""
        if perm not in ACL.get(agent, {}).get(short, set()):
            raise Denied(f"{agent} has no {perm} on {self.ds(short)}")

    async def health(self) -> str:
        if self.target == "offline":
            return "off"
        try:
            await self.get("/api/v1/datasets", timeout=6.0)
            return "connected"
        except Exception:
            return "unreachable"

    async def dataset_id(self, short: str) -> str | None:
        name = self.ds(short)
        if name in self._ids or self.target == "offline":
            return self._ids.get(name)
        for row in await self.get("/api/v1/datasets") or []:
            if row.get("name") and row.get("id"):
                self._ids[row["name"]] = str(row["id"])
        return self._ids.get(name)

    # ---------- remember ----------

    async def remember(self, text: str, *, title: str, tags: list[str], dataset: str, agent: str, session_id: str | None = None, background: bool = False) -> tuple[list[str], MemoryEvent]:
        """Permanent graph when session_id is None, the session tier otherwise. Returns Cognee data ids."""
        t0 = time.perf_counter()
        name = self.ds(dataset)
        tier = f"session {session_id}" if session_id else name
        if self.target == "offline":
            try:
                self._check(agent, dataset, "write")
            except Denied as err:
                return [], await self._log("remember", f"denied: {err}", t0, False, agent=agent, dataset=name, session_id=session_id)
            item_id = uuid.uuid4().hex
            items = await self.store.get(OFFLINE_KEY) or []
            items.append({"id": item_id, "title": title, "text": text, "tags": tags, "dataset": dataset, "session_id": session_id, "at": _now().isoformat()})
            await self.store.set(OFFLINE_KEY, items)
            return [item_id], await self._log("remember", f"{title} -> {tier}", t0, True, agent=agent, dataset=name, session_id=session_id, detail={"tags": tags})
        form: list[tuple[str, str]] = [("datasetName", name)]
        form += [("node_set", t) for t in tags]
        if session_id:
            form.append(("session_id", session_id))
        if background:
            form.append(("run_in_background", "true"))
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", title)[:60] or "note"
        files = {"data": (f"{safe}.txt", text.encode("utf-8"), "text/plain")}
        try:
            result = await self.post("/api/v1/remember", agent=agent, data=form, files=files)
            ids = _find_ids(result)
            return ids, await self._log("remember", f"{title} -> {tier}", t0, True, agent=agent, dataset=name, session_id=session_id, detail={"tags": tags, "dataIds": ids})
        except Denied as err:
            return [], await self._log("remember", f"denied: {err}", t0, False, agent=agent, dataset=name, session_id=session_id)
        except Exception as err:
            return [], await self._log("remember", f"{title} failed: {err}", t0, False, agent=agent, dataset=name, session_id=session_id)

    async def entry(self, entry: dict, *, dataset: str, agent: str, session_id: str | None, skill_improvement: dict | None = None, label: str = "") -> tuple[dict, MemoryEvent]:
        """Typed entries: qa, feedback (session tier) and skill_run (graph; drives skill self-improvement)."""
        t0 = time.perf_counter()
        name = self.ds(dataset)
        label = label or f"{entry.get('type')} entry"
        if self.target == "offline":
            out: dict = {"entry_id": uuid.uuid4().hex}
            if skill_improvement and entry.get("type") == "skill_run" and (entry.get("success_score") or 1) < skill_improvement.get("score_threshold", 0.9):
                out["items"] = [{"kind": "skill_improvement_proposal", "proposal_id": f"prop_{uuid.uuid4().hex[:8]}"}]
            return out, await self._log("entry", label, t0, True, agent=agent, dataset=name, session_id=session_id)
        payload: dict[str, Any] = {"entry": entry, "dataset_name": name, "session_id": session_id}
        if skill_improvement:
            payload["skill_improvement"] = skill_improvement
        try:
            result = await self.post("/api/v1/remember/entry", agent=agent, json=payload)
            return result, await self._log("entry", label, t0, True, agent=agent, dataset=name, session_id=session_id)
        except Exception as err:
            return {}, await self._log("entry", f"{label} failed: {err}", t0, False, agent=agent, dataset=name, session_id=session_id)

    # ---------- recall ----------

    async def recall(self, query: str, *, datasets: list[str], agent: str, session_id: str | None = None, top_k: int = 8) -> tuple[str, list[Source], MemoryEvent]:
        t0 = time.perf_counter()
        names = [self.ds(d) for d in datasets]
        if self.target == "offline":
            allowed = [d for d in datasets if "read" in ACL.get(agent, {}).get(d, set())]
            if not allowed:
                return "", [], await self._log("recall", f"denied: {agent} can't read {', '.join(names)}", t0, False, agent=agent, dataset=",".join(names), session_id=session_id)
            items = [it for it in await self.store.get(OFFLINE_KEY) or [] if it["dataset"] in allowed and (it["session_id"] in (None, session_id))]
            q = _words(query)
            hits = sorted((it for it in items if q & _words(it["title"] + " " + it["text"])), key=lambda it: len(q & _words(it["title"] + " " + it["text"])), reverse=True)[:top_k]
            answer = "\n".join(f"- {h['title']}: {h['text'][:220]}" for h in hits) or "Nothing in memory about that yet."
            refs = [Source(title=h["title"], kind="human", quote=h["text"][:90]) for h in hits]
            return answer, refs, await self._log("recall", f"\"{query[:64]}\" -> {len(hits)} memories", t0, True, agent=agent, dataset=",".join(names), session_id=session_id)
        payload: dict[str, Any] = {"query": query, "datasets": names, "top_k": top_k, "include_references": True}
        if session_id:
            payload["session_id"] = session_id
        try:
            rows = await self.post("/api/v1/recall", agent=agent, json=payload, timeout=90.0)
            answer, refs = _read_recall(rows)
            return answer, refs, await self._log("recall", f"\"{query[:64]}\" -> {len(refs)} references", t0, True, agent=agent, dataset=",".join(names), session_id=session_id)
        except Denied:
            return "", [], await self._log("recall", f"denied: {agent} can't read {', '.join(names)}", t0, False, agent=agent, dataset=",".join(names), session_id=session_id)
        except Exception as err:
            return "", [], await self._log("recall", f"recall failed: {err}", t0, False, agent=agent, dataset=",".join(names), session_id=session_id)

    # ---------- improve: self-improvement ----------

    async def improve(self, *, dataset: str, agent: str, session_ids: list[str] | None = None, review_conflicts: bool = True) -> tuple[dict, MemoryEvent]:
        t0 = time.perf_counter()
        name = self.ds(dataset)
        what = f"distil {len(session_ids)} session(s) into {name}" if session_ids else f"enrich {name}"
        what += " + conflict review" if review_conflicts else ""
        if self.target == "offline":
            return {"offline": True}, await self._log("improve", what, t0, True, agent=agent, dataset=name)
        payload: dict[str, Any] = {"dataset_name": name, "review_conflicts": review_conflicts}
        if session_ids:
            payload["session_ids"] = session_ids
        try:
            result = await self.post("/api/v1/improve", agent=agent, json=payload, timeout=240.0)
            return result, await self._log("improve", what, t0, True, agent=agent, dataset=name, detail={"stages": _stage_names(result)})
        except Exception as err:
            return {}, await self._log("improve", f"improve failed: {err}", t0, False, agent=agent, dataset=name)

    # ---------- conflicts ----------

    async def conflicts(self, *, dataset: str, agent: str, status: str = "unresolved") -> tuple[list[dict], MemoryEvent]:
        t0 = time.perf_counter()
        name = self.ds(dataset)
        if self.target == "offline":
            return [], await self._log("conflicts", "offline: Clawback builds the conflict from the two sources", t0, True, agent=agent, dataset=name)
        try:
            ds_id = await self.dataset_id(dataset)
            rows = await self.get("/api/v1/conflicts", agent=agent, params={"dataset_id": ds_id, "status": status}) if ds_id else []
            return rows or [], await self._log("conflicts", f"{len(rows or [])} {status} conflict(s) in {name}", t0, True, agent=agent, dataset=name)
        except Exception as err:
            return [], await self._log("conflicts", f"conflicts failed: {err}", t0, False, agent=agent, dataset=name)

    async def resolve(self, conflict_id: str, fact_id: str, reason: str, *, dataset: str, agent: str) -> MemoryEvent:
        t0 = time.perf_counter()
        name = self.ds(dataset)
        if self.target == "offline":
            return await self._log("resolve", f"human chose: {reason[:60]}", t0, True, agent=agent, dataset=name)
        try:
            ds_id = await self.dataset_id(dataset)
            await self.post(f"/api/v1/conflicts/{conflict_id}/resolve", agent=agent, json={"datasetId": ds_id, "selectedFactId": fact_id, "reason": reason})
            return await self._log("resolve", f"human chose: {reason[:60]}", t0, True, agent=agent, dataset=name)
        except Exception as err:
            return await self._log("resolve", f"resolve failed: {err}", t0, False, agent=agent, dataset=name)

    # ---------- forget ----------

    async def forget(self, data_ids: list[str], why: str, *, dataset: str, agent: str) -> MemoryEvent:
        t0 = time.perf_counter()
        name = self.ds(dataset)
        if self.target == "offline":
            items = await self.store.get(OFFLINE_KEY) or []
            keep = [it for it in items if it["id"] not in set(data_ids)]
            await self.store.set(OFFLINE_KEY, keep)
            return await self._log("forget", f"{len(items) - len(keep)} item(s): {why}", t0, True, agent=agent, dataset=name)
        removed, errors = 0, []
        for data_id in data_ids:
            try:
                await self.post("/api/v1/forget", agent=agent, json={"dataId": data_id, "dataset": name})
                removed += 1
            except Exception as err:
                errors.append(str(err))
        return await self._log("forget", f"{removed} item(s): {why}", t0, not errors, agent=agent, dataset=name, detail={"errors": errors[:2]})


def _find_ids(result: Any) -> list[str]:
    """Pulls data ids out of a remember response, whatever its exact shape."""
    ids: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key in ("data_id", "dataId"):
                if isinstance(node.get(key), str):
                    ids.append(node[key])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(result)
    return sorted(set(ids))


def find_proposal(result: Any) -> str | None:
    items = result.get("items", []) if isinstance(result, dict) else getattr(result, "items", [])
    for item in items or []:
        if isinstance(item, dict) and item.get("kind") == "skill_improvement_proposal":
            return str(item.get("proposal_id"))
    return None


def _read_recall(rows: Any) -> tuple[str, list[Source]]:
    """Recall returns a list of results; take the text answer and any references."""
    texts: list[str] = []
    refs: list[Source] = []
    for row in rows if isinstance(rows, list) else [rows]:
        if isinstance(row, str):
            texts.append(row)
            continue
        if not isinstance(row, dict):
            continue
        for key in ("answer", "text", "search_result", "result", "content"):
            val = row.get(key)
            if isinstance(val, str) and val.strip():
                texts.append(val.strip())
                break
            if isinstance(val, list):
                texts.extend(str(v) for v in val if v)
                break
        for ref in row.get("references") or []:
            if isinstance(ref, dict):
                title = ref.get("name") or ref.get("title") or ref.get("source") or "memory"
                refs.append(Source(title=str(title)[:80], quote=str(ref.get("text") or ref.get("snippet") or "")[:90], kind="human"))
    return "\n".join(texts[:4]), refs[:8]


def _stage_names(result: Any) -> list[str]:
    if isinstance(result, dict):
        stages = result.get("stages") or result.get("stage_results") or []
        if isinstance(stages, list):
            return [str(s.get("name", s)) if isinstance(s, dict) else str(s) for s in stages][:12]
    return []
