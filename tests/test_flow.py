"""The whole demo, end to end, offline (snapshots + offline memory + templates). Run: python -m pytest -q"""

import os
import sys
from pathlib import Path

os.environ["CLAWBACK_DEMO"] = "1"
for key in ("COGNEE_URL", "ANTHROPIC_API_KEY", "UPSTASH_REDIS_REST_URL", "KV_REST_API_URL"):
    os.environ.pop(key, None)

import importlib.util  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

# api/ is Vercel's functions folder, not a package: load api/index.py by path.
_spec = importlib.util.spec_from_file_location("clawback_api", Path(__file__).resolve().parents[1] / "api" / "index.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
app = _mod.app

client = TestClient(app)


def test_full_demo_flow():
    assert client.post("/api/py/reset").status_code == 200
    health = client.get("/api/py/health").json()
    assert health["mode"] == "demo" and health["cognee"] == "off"

    vendors = client.get("/api/py/vendors").json()
    assert {v["id"] for v in vendors} == {"github", "twilio", "cloudflare"}

    team = client.post("/api/py/agents/setup").json()
    assert set(team["agents"]) == {"auditor", "claims-writer", "inbox-assistant"}
    perms = {(r["agent"], r["dataset"].split("_")[-1]): r["allowed"] for r in client.get("/api/py/agents/permissions").json()}
    assert perms[("inbox-assistant", "playbook")] is False  # the permissions moment
    assert perms[("claims-writer", "playbook")] is True and perms[("auditor", "promises")] is True

    seeded = client.post("/api/py/seed").json()
    assert len(seeded) == 3 and all(e["op"] == "remember" for e in seeded)

    audit = client.post("/api/py/audit", json={"vendorId": "github"}).json()
    assert audit["windowStart"].startswith("2026-10-01")
    assert audit["owedUsd"] > 0 and audit["breached"] is True
    assert audit["worstComponent"]

    claim = client.post("/api/py/claims", json={"auditId": audit["id"]}).json()
    assert claim["status"] == "draft" and "GitHub" in claim["email"]["body"]

    claim = client.post(f"/api/py/claims/{claim['id']}/send").json()
    assert claim["status"] == "sent"

    reply = "Thanks for reaching out. Our records show only 45 minutes of qualifying downtime, since we only count full outages."
    claim = client.post(f"/api/py/claims/{claim['id']}/reply", json={"text": reply, "sender": "GitHub Support"}).json()
    assert claim["status"] == "contested"
    facts = claim["conflict"]["facts"]
    assert {f["id"] for f in facts} == {"status_page", "vendor_reply"}

    claim = client.post(f"/api/py/claims/{claim['id']}/resolve", json={"selectedFactId": "status_page", "reason": "Their own status page shows longer"}).json()
    assert claim["status"] == "sent" and claim["lessons"]
    assert claim["email"]["subject"].startswith("Re: ")

    proposal = client.get(f"/api/py/claims/{claim['id']}/proposal").json()
    assert proposal["proposalId"]
    assert client.post(f"/api/py/claims/{claim['id']}/proposal/apply").json()["ok"] is True

    claim = client.post(f"/api/py/claims/{claim['id']}/paid").json()
    assert claim["status"] == "paid" and claim["memoryDataIds"] == []

    briefing = client.post("/api/py/handoff").json()
    assert briefing["recalledFrom"] == "offline" and briefing["summary"]

    ops = [e["op"] for e in client.get("/api/py/memory").json()]
    for op in ("remember", "recall", "improve", "forget", "entry"):
        assert op in ops, op


def test_unknown_vendor_is_404():
    assert client.post("/api/py/audit", json={"vendorId": "nope"}).status_code == 404
