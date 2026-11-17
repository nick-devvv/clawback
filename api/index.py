"""Clawback API (FastAPI). On Vercel this file is a Python function; next.config.mjs sends every
/api/py/* request here. Locally: `npm run dev:api` (uvicorn on port 8001).

Routes are the contract in docs/API.md. Keep this file thin: parse, call the agent, return.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from clawback.agent import Agent, NotFound  # noqa: E402
from clawback.models import (  # noqa: E402
    AskRequest,
    AskResult,
    Audit,
    AuditRequest,
    Briefing,
    Claim,
    Health,
    IngestRequest,
    IngestResult,
    MemoryEvent,
    ReplyRequest,
    ResolveRequest,
    Vendor,
)
from clawback import inbox  # noqa: E402
from clawback.vendors import all_vendors  # noqa: E402

app = FastAPI(title="Clawback API", version="0.1.0", docs_url="/api/py/docs", openapi_url="/api/py/openapi.json")

# Same origin on Vercel; CORS only matters if the frontend calls a backend on another URL (NEXT_PUBLIC_API_BASE).
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def agent() -> Agent:
    return Agent()


def _nf(err: NotFound) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "not_found", "message": str(err)})


@app.get("/api/py/health", response_model=Health)
async def health():
    return await agent().health()


@app.get("/api/py/vendors", response_model=list[Vendor])
async def vendors():
    return all_vendors()


@app.post("/api/py/seed", response_model=list[MemoryEvent])
async def seed():
    return await agent().seed()


@app.post("/api/py/ingest", response_model=IngestResult)
async def ingest(req: IngestRequest):
    try:
        return await agent().ingest(req)
    except NotFound as err:
        raise _nf(err)


@app.post("/api/py/audit", response_model=Audit)
async def audit(req: AuditRequest):
    try:
        return await agent().audit(req)
    except NotFound as err:
        raise _nf(err)


@app.post("/api/py/claims", response_model=Claim)
async def draft(body: dict):
    audit_id = body.get("auditId") or body.get("audit_id")
    if not audit_id:
        raise HTTPException(status_code=422, detail={"code": "missing_audit_id", "message": "Send {auditId}."})
    try:
        return await agent().draft(audit_id)
    except NotFound as err:
        raise _nf(err)


@app.get("/api/py/claims", response_model=list[Claim])
async def claims():
    return await agent().list_claims()


@app.get("/api/py/claims/{claim_id}", response_model=Claim)
async def claim(claim_id: str):
    try:
        return await agent().get_claim(claim_id)
    except NotFound as err:
        raise _nf(err)


@app.post("/api/py/claims/{claim_id}/send", response_model=Claim)
async def send(claim_id: str):
    try:
        return await agent().send(claim_id)
    except NotFound as err:
        raise _nf(err)


@app.post("/api/py/claims/{claim_id}/reply", response_model=Claim)
async def reply(claim_id: str, req: ReplyRequest):
    try:
        return await agent().reply(claim_id, req)
    except NotFound as err:
        raise _nf(err)


@app.post("/api/py/claims/{claim_id}/resolve", response_model=Claim)
async def resolve(claim_id: str, req: ResolveRequest):
    try:
        return await agent().resolve(claim_id, req)
    except NotFound as err:
        raise _nf(err)


@app.post("/api/py/claims/{claim_id}/paid", response_model=Claim)
async def paid(claim_id: str):
    try:
        return await agent().paid(claim_id)
    except NotFound as err:
        raise _nf(err)


@app.post("/api/py/agents/setup")
async def agents_setup():
    """Creates the 3 datasets, 3 Cognee agents with their own keys, the grants, and the claim-writer skill."""
    return await agent().setup_agents()


@app.get("/api/py/agents/permissions")
async def agents_permissions():
    """Each agent tries to read each dataset. Inbox Assistant -> playbook comes back denied."""
    return await agent().permission_check()


@app.get("/api/py/claims/{claim_id}/proposal")
async def skill_proposal(claim_id: str):
    """Cognee's proposed rewrite of the claim-writer skill after a pushback (before/after)."""
    try:
        return await agent().proposal(claim_id)
    except NotFound as err:
        raise _nf(err)


@app.post("/api/py/claims/{claim_id}/proposal/apply")
async def apply_skill_proposal(claim_id: str):
    try:
        return await agent().apply_proposal(claim_id)
    except NotFound as err:
        raise _nf(err)


@app.get("/api/py/inbox")
async def inbox_emails(vendor_id: str):
    """Vendor emails from the inbox (Slashy MCP when connected, sample emails otherwise)."""
    return await inbox.vendor_emails(vendor_id)


@app.post("/api/py/ask", response_model=AskResult)
async def ask(req: AskRequest):
    return await agent().ask(req)


@app.post("/api/py/handoff", response_model=Briefing)
async def handoff():
    return await agent().handoff()


@app.get("/api/py/memory", response_model=list[MemoryEvent])
async def memory_log(limit: int = 60):
    return await agent().memory.log(limit)


@app.post("/api/py/reset")
async def reset(memory: bool = False):
    return await agent().reset(memory_too=memory)
