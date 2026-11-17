"""Vendor configs live in data/vendors/*.json, one per vendor, with the SLA terms checked against each
vendor's published SLA page (the URL is in promise.source). Add a vendor by adding a file: any
company on an Atlassian Statuspage works (its feed is {statusPage}/api/v2/incidents.json)."""

from __future__ import annotations

import json
from functools import lru_cache

from .config import DATA
from .models import Vendor


@lru_cache(maxsize=1)
def _load() -> dict[str, Vendor]:
    out: dict[str, Vendor] = {}
    for path in sorted((DATA / "vendors").glob("*.json")):
        raw = json.loads(path.read_text())
        raw.pop("_note", None)
        vendor = Vendor.model_validate(raw)
        out[vendor.id] = vendor
    return out


def all_vendors() -> list[Vendor]:
    return list(_load().values())


def get_vendor(vendor_id: str) -> Vendor | None:
    return _load().get(vendor_id)


def vendor_note(vendor_id: str) -> str:
    path = DATA / "vendors" / f"{vendor_id}.json"
    if not path.exists():
        return ""
    return json.loads(path.read_text()).get("_note", "")
