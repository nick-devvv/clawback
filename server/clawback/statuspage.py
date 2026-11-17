"""Reads a vendor's public incident history from its Atlassian Statuspage.

Every Statuspage site serves the same public JSON, no key needed:
    GET {status_page}/api/v2/incidents.json   -> the 50 most recent incidents
Each incident has: id, name, impact (none/minor/major/critical/maintenance), created_at, started_at,
resolved_at, shortlink, components[{name}], incident_updates[...].

Live fetch first; if it fails or times out, read data/status/{vendor_id}.json (written by
scripts/snapshot_status.py). Snapshot the feeds at the start of the event so the demo never depends
on a third-party site being up.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal

import httpx

from .config import DATA
from .models import Incident, Vendor

UA = {"User-Agent": "clawback-hackathon/0.1 (+https://github.com/nick-devvv/clawback)", "Accept": "application/json"}


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_incidents(payload: dict) -> list[Incident]:
    out: list[Incident] = []
    for raw in payload.get("incidents", []) or []:
        started = _dt(raw.get("started_at")) or _dt(raw.get("created_at"))
        if started is None:
            continue
        status = raw.get("status") or ""
        resolved = _dt(raw.get("resolved_at"))
        if resolved is None and status in ("resolved", "postmortem", "completed"):
            # Some feeds mark an incident resolved but leave resolved_at empty: use its last update.
            stamps = [_dt(u.get("created_at")) for u in (raw.get("incident_updates") or [])]
            stamps = [t for t in stamps if t]
            resolved = max(stamps) if stamps else _dt(raw.get("updated_at"))
        end = resolved or datetime.now(timezone.utc)
        impact = raw.get("impact") or "none"
        if impact not in ("none", "minor", "major", "critical", "maintenance"):
            impact = "none"
        comps = [c.get("name", "") for c in (raw.get("components") or []) if c.get("name")]
        out.append(
            Incident(
                id=str(raw.get("id", "")),
                name=raw.get("name", "Untitled incident"),
                impact=impact,
                started_at=started,
                resolved_at=resolved,
                minutes=round(max(0.0, (end - started).total_seconds() / 60.0), 1),
                components=comps,
                url=raw.get("shortlink") or "",
                status=status,
            )
        )
    out.sort(key=lambda i: i.started_at, reverse=True)
    return out


def snapshot_path(vendor_id: str):
    return DATA / "status" / f"{vendor_id}.json"


def load_snapshot(vendor_id: str) -> dict | None:
    path = snapshot_path(vendor_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())


async def fetch_payload(vendor: Vendor, live: bool = True, timeout: float = 6.0) -> tuple[dict, Literal["live", "snapshot", "none"]]:
    if live:
        url = f"{vendor.status_page.rstrip('/')}/api/v2/incidents.json"
        try:
            async with httpx.AsyncClient(timeout=timeout, headers=UA, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.json(), "live"
        except (httpx.HTTPError, ValueError):
            pass
    snap = load_snapshot(vendor.id)
    if snap is not None:
        return snap, "snapshot"
    return {"incidents": []}, "none"


async def fetch_incidents(vendor: Vendor, live: bool = True) -> tuple[list[Incident], Literal["live", "snapshot", "none"]]:
    payload, source = await fetch_payload(vendor, live=live)
    return parse_incidents(payload), source
