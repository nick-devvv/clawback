"""The inbox. Vendor promises often live in email (renewals, account-manager notes), and claims go out by email.

Slashy (an AI email client; free for a month for this event) exposes a user's inbox over MCP ("Slashy MCP").
P1 for Darian: get the MCP URL and token from the Slashy team, then implement the two calls below over
MCP JSON-RPC (`tools/list` once to learn the tool names, then `tools/call`). Until then this reads the
sample emails in data/emails/, which are labelled as fictional.

Interface the rest of the app relies on:
    await vendor_emails(vendor_id)  -> [{"title", "text", "date", "from"}]
    await create_draft(to, subject, body) -> {"ok": bool, "where": "slashy" | "none"}
"""

from __future__ import annotations

import os

from .config import DATA

SLASHY_MCP_URL = os.environ.get("SLASHY_MCP_URL", "")
SLASHY_TOKEN = os.environ.get("SLASHY_TOKEN", "")


async def vendor_emails(vendor_id: str) -> list[dict]:
    if SLASHY_MCP_URL and SLASHY_TOKEN:
        pass  # TODO(darian): search the inbox for mail from this vendor through Slashy MCP
    out = []
    for path in sorted((DATA / "emails").glob(f"{vendor_id}-*.txt")):
        out.append({"title": path.stem.replace("-", " "), "text": path.read_text(), "date": "", "from": f"{vendor_id} (sample)"})
    return out


async def create_draft(to: str, subject: str, body: str) -> dict:
    if SLASHY_MCP_URL and SLASHY_TOKEN:
        pass  # TODO(darian): create a draft in the user's inbox through Slashy MCP, return {"ok": True, "where": "slashy"}
    return {"ok": False, "where": "none"}
