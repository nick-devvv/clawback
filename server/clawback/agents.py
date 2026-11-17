"""Shared memory across agents, with permissions. Three agents work one claim, each with its own Cognee
identity, all reading and writing the same memory, but not all of it:

  Auditor          reads status pages, writes promises + evidence      promises: read/write
  Claims Writer    writes and defends claims, learns from pushback      promises: read · claims + playbook: read/write
  Inbox Assistant  handles vendor mail (Slashy), sees claims, never     promises + claims: read · playbook: none
                   our negotiation playbook

setup() makes it real in Cognee:
  POST /api/v1/datasets {name}                                   x3 datasets
  POST /api/v1/agents/create?name=...                            x3 agent users, each with its own API key
  POST /api/v1/permissions/datasets/{agent_id}?permission_name=  grants from memory.ACL
  POST /api/v1/skills {skills_text, skill_name, dataset_name}    the claim-writer skill, for self-improvement
Run it once (POST /api/py/agents/setup). Agent keys stay server-side in the store.
"""

from __future__ import annotations

import time

from .config import DATA
from .memory import ACL, AGENT_KEYS, AUDITOR, CLAIMS, INBOX, OWNER, PLAYBOOK, PROMISES, WRITER, Denied, Memory

AGENTS = {
    AUDITOR: "Reads vendor status pages and SLAs; records promises and evidence.",
    WRITER: "Drafts and defends claims; learns each vendor's habits.",
    INBOX: "Handles vendor email through Slashy; sees claims, not the playbook.",
}
SKILL_NAME = "claim-writer"


async def setup(memory: Memory) -> dict:
    report: dict = {"datasets": {}, "agents": {}, "grants": [], "skill": None, "target": memory.target}
    t0 = time.perf_counter()
    if memory.target == "offline":
        report["agents"] = {name: {"id": f"offline-{name}"} for name in AGENTS}
        report["grants"] = [f"{a} {sorted(p)} {memory.ds(d)}" for a, perms in ACL.items() if a != OWNER for d, p in perms.items() if p]
        report["skill"] = SKILL_NAME
        await memory._log("health", "offline: 3 agents, permission table enforced locally", t0, True, agent=OWNER)
        return report
    for short in (PROMISES, CLAIMS, PLAYBOOK):
        row = await memory.post("/api/v1/datasets", json={"name": memory.ds(short)})
        report["datasets"][short] = str(row.get("id"))
        memory._ids[memory.ds(short)] = str(row.get("id"))
    keys = await memory.store.get(AGENT_KEYS) or {}
    for name in AGENTS:
        if name not in keys:
            try:
                created = await memory.post("/api/v1/agents/create", params={"name": f"clawback-{name}"})
                keys[name] = {"id": created.get("agentId") or created.get("agent_id"), "key": created.get("agentApiKey") or created.get("agent_api_key")}
            except RuntimeError as err:  # 409: exists from an earlier run, key not shown again
                report["agents"][name] = {"error": str(err)[:160]}
                continue
        report["agents"][name] = {"id": keys[name]["id"]}
    await memory.store.set(AGENT_KEYS, keys)
    for name, perms in ACL.items():
        if name == OWNER or name not in keys:
            continue
        for short, granted in perms.items():
            for perm in sorted(granted):
                await memory.post(f"/api/v1/permissions/datasets/{keys[name]['id']}", params={"permission_name": perm}, json=[report["datasets"][short]])
                report["grants"].append(f"{name} {perm} {memory.ds(short)}")
    skill_text = (DATA / "skills" / SKILL_NAME / "SKILL.md").read_text()
    await memory.post("/api/v1/skills", json={"skills_text": skill_text, "skill_name": SKILL_NAME, "dataset_name": memory.ds(PLAYBOOK)})
    report["skill"] = SKILL_NAME
    await memory._log("health", f"3 agents, {len(report['grants'])} grants, skill {SKILL_NAME}", t0, True, agent=OWNER)
    return report


async def permission_check(memory: Memory) -> list[dict]:
    """The permissions moment in the demo: each agent tries to read each dataset; Cognee answers."""
    rows = []
    for agent in (AUDITOR, WRITER, INBOX):
        for short in (PROMISES, CLAIMS, PLAYBOOK):
            _, _, ev = await memory.recall("What do we know?", datasets=[short], agent=agent, top_k=1)
            rows.append({"agent": agent, "dataset": memory.ds(short), "allowed": ev.ok, "summary": ev.summary})
    return rows


async def proposal(memory: Memory, proposal_id: str) -> dict:
    """Before/after of a skill rewrite Cognee proposed (GET /api/v1/proposals/{id}?dataset_id=)."""
    if memory.target == "offline":
        return {"proposalId": proposal_id, "offline": True}
    ds_id = await memory.dataset_id(PLAYBOOK)
    try:
        return await memory.get(f"/api/v1/proposals/{proposal_id}", agent=WRITER, params={"dataset_id": ds_id})
    except (Denied, RuntimeError) as err:
        return {"proposalId": proposal_id, "error": str(err)[:200]}
