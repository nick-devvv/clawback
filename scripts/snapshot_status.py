"""Saves each vendor's live incident feed to data/status/{vendor}.json, so the demo has real data even
if a status page is slow or down. Run at the start of the event, and again right before judging:

    python scripts/snapshot_status.py
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

import httpx  # noqa: E402

from clawback.statuspage import UA, snapshot_path  # noqa: E402
from clawback.vendors import all_vendors  # noqa: E402


async def main() -> None:
    async with httpx.AsyncClient(timeout=15, headers=UA, follow_redirects=True) as client:
        for v in all_vendors():
            url = f"{v.status_page.rstrip('/')}/api/v2/incidents.json"
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                snapshot_path(v.id).write_text(json.dumps(data, indent=1))
                print(f"{v.id:<11} {len(data.get('incidents', [])):>3} incidents  <- {url}")
            except Exception as err:  # keep the old snapshot if the fetch fails
                print(f"{v.id:<11} FAILED ({err}); kept the existing snapshot")


if __name__ == "__main__":
    asyncio.run(main())
