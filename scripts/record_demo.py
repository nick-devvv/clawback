"""Runs the whole demo against a running API and saves every response to data/demo/recorded.json.
The frontend replays this file when the API is down (DEMO mode), so the demo can't fail on stage.

    npm run dev:api            # in one terminal
    python scripts/record_demo.py http://127.0.0.1:8001
"""

import json
import sys
from pathlib import Path

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001").rstrip("/") + "/api/py"
OUT = Path(__file__).resolve().parents[1] / "data" / "demo" / "recorded.json"
REPLY = (Path(__file__).resolve().parents[1] / "data" / "emails" / "github-pushback.txt").read_text()


def main() -> None:
    c = httpx.Client(timeout=300)
    rec: dict = {}
    c.post(f"{BASE}/reset")
    rec["health"] = c.get(f"{BASE}/health").json()
    rec["vendors"] = c.get(f"{BASE}/vendors").json()
    rec["team"] = c.post(f"{BASE}/agents/setup").json()
    rec["permissions"] = c.get(f"{BASE}/agents/permissions").json()
    rec["seed"] = c.post(f"{BASE}/seed").json()
    rec["audits"] = {v["id"]: c.post(f"{BASE}/audit", json={"vendorId": v["id"]}).json() for v in rec["vendors"]}
    claim = c.post(f"{BASE}/claims", json={"auditId": rec["audits"]["github"]["id"]}).json()
    rec["draft"] = claim
    rec["sent"] = c.post(f"{BASE}/claims/{claim['id']}/send").json()
    rec["contested"] = c.post(f"{BASE}/claims/{claim['id']}/reply", json={"text": REPLY, "sender": "GitHub Support"}).json()
    fact = next(f["id"] for f in rec["contested"]["conflict"]["facts"] if f["source"]["kind"] == "status_page" or f["id"] == "status_page")
    rec["resolved"] = c.post(f"{BASE}/claims/{claim['id']}/resolve", json={"selectedFactId": fact, "reason": "Their own status page shows longer"}).json()
    rec["proposal"] = c.get(f"{BASE}/claims/{claim['id']}/proposal").json()
    rec["applied"] = c.post(f"{BASE}/claims/{claim['id']}/proposal/apply").json()
    rec["paid"] = c.post(f"{BASE}/claims/{claim['id']}/paid").json()
    rec["handoff"] = c.post(f"{BASE}/handoff").json()
    rec["memory"] = c.get(f"{BASE}/memory").json()
    OUT.write_text(json.dumps(rec, indent=1))
    print(f"saved {OUT} (mode {rec['health']['mode']}, cognee {rec['health']['cognee']})")


if __name__ == "__main__":
    main()
