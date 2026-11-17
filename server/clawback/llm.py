"""Claude does three jobs: read a pasted email for promises, read a vendor's reply for their story,
and write the claim email. Each job has a rules-or-template fallback, so the flow works with no key
(and the UI says which one ran)."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .config import Settings
from .models import Audit, Email

API = "https://api.anthropic.com/v1/messages"


class LLM:
    def __init__(self, settings: Settings):
        self.s = settings
        self.name = "claude" if settings.llm_enabled else "off"

    async def _json(self, system: str, user: str, max_tokens: int = 1200) -> Any | None:
        if not self.s.llm_enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.post(
                    API,
                    headers={"x-api-key": self.s.anthropic_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={
                        "model": self.s.anthropic_model,
                        "max_tokens": max_tokens,
                        "system": system + "\nReply with one JSON value only. No prose, no code fences.",
                        "messages": [{"role": "user", "content": user}],
                    },
                )
                resp.raise_for_status()
                text = "".join(b.get("text", "") for b in resp.json().get("content", []) if b.get("type") == "text")
                text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                return json.loads(text)
        except Exception:
            return None

    # ---------- 1. promises in an email or contract ----------

    async def extract_promises(self, vendor_name: str, text: str) -> list[dict]:
        system = (
            "You read vendor contracts and emails for a startup and pull out uptime promises with credit terms. "
            "Return a JSON list. Each item: {service, targetPct (number), window ('month'|'quarter'), "
            "tiers: [{threshold, inclusive (bool), creditPct}], feeBasis, claimDeadlineDays (int), claimHow, "
            "quote (the exact words, under 15 words), confidence (0-1)}. Return [] if there is no such promise."
        )
        data = await self._json(system, f"Vendor: {vendor_name}\n\n{text[:12000]}")
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict) and d.get("targetPct")]
        return rule_promises(text)

    # ---------- 2. the vendor's reply ----------

    async def read_reply(self, text: str) -> dict:
        system = (
            "A vendor replied to a service-credit claim. Return {claimedDowntimeMinutes (number or null), "
            "position (one short sentence: what the vendor says), countsOnly (what they say counts as downtime, or ''), "
            "lesson (one sentence: what to do differently next time when claiming from this vendor)}."
        )
        data = await self._json(system, text[:6000], max_tokens=500)
        if isinstance(data, dict):
            return data
        return rule_reply(text)

    # ---------- 3. the claim email ----------

    async def draft_claim(self, audit: Audit, lessons: list[str], company: str = "our team") -> Email:
        system = (
            "Write a short, firm, polite service-credit claim email from a startup to a vendor. "
            "Use only the facts given. Cite the SLA clause and each counted incident with its link. "
            "Apply every lesson given. Return {subject, body}. Body under 220 words, plain text."
        )
        facts = audit_facts(audit)
        user = json.dumps({"company": company, "facts": facts, "lessons": lessons})
        data = await self._json(system, user, max_tokens=900)
        if isinstance(data, dict) and data.get("subject") and data.get("body"):
            return Email(subject=data["subject"], body=data["body"])
        return template_claim(audit, lessons, company)


# ---------- fallbacks ----------


def rule_promises(text: str) -> list[dict]:
    """Finds '99.9% ... uptime' and '10% credit' style sentences without a model."""
    target = re.search(r"(\d{2,3}(?:\.\d+)?)\s*%[^.\n]{0,60}(?:uptime|availability)", text, re.I)
    if not target:
        target = re.search(r"(?:uptime|availability)[^.\n]{0,60}?(\d{2,3}(?:\.\d+)?)\s*%", text, re.I)
    credit = re.search(r"(\d{1,3})\s*%[^.\n]{0,40}(?:credit|back|refund)", text, re.I)
    if not target:
        return []
    window = "quarter" if re.search(r"quarter", text, re.I) else "month"
    sentence = re.search(r"[^.\n]*" + re.escape(target.group(0)) + r"[^.\n]*", text)
    quote = " ".join((sentence.group(0) if sentence else target.group(0)).split()[:14])
    return [
        {
            "service": "Service",
            "targetPct": float(target.group(1)),
            "window": window,
            "tiers": [{"threshold": float(target.group(1)), "inclusive": False, "creditPct": float(credit.group(1)) if credit else 10.0}],
            "feeBasis": "fees for the affected service in the period",
            "claimDeadlineDays": 30,
            "claimHow": "Email your account manager or support",
            "quote": quote,
            "confidence": 0.6,
        }
    ]


def rule_reply(text: str) -> dict:
    minutes = None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(minutes|minute|mins|min)\b", text, re.I)
    h = re.search(r"(\d+(?:\.\d+)?)\s*(hours|hour|hrs|hr)\b", text, re.I)
    if m:
        minutes = float(m.group(1))
    elif h:
        minutes = float(h.group(1)) * 60
    first = re.split(r"(?<=[.!?])\s", text.strip())
    position = next((s for s in first if len(s.split()) > 4), text.strip()[:140])
    return {
        "claimedDowntimeMinutes": minutes,
        "position": position[:200],
        "countsOnly": "",
        "lesson": "Attach each incident's status-page link with its start and resolve times, and quote the SLA clause.",
    }


def audit_facts(audit: Audit) -> dict:
    counted = [i for i in audit.incidents if i.counted]
    return {
        "vendor": audit.vendor_name,
        "service": audit.promise.service,
        "promise": audit.rule_text,
        "slaSource": {"title": audit.promise.source.title, "url": audit.promise.source.url, "quote": audit.promise.source.quote},
        "window": f"{audit.window_start.date()} to {audit.window_end.date()}",
        "uptimePct": audit.uptime_pct,
        "downtimeMinutes": audit.downtime_minutes,
        "creditPct": audit.credit_pct,
        "owedUsd": audit.owed_usd,
        "claimBy": str(audit.claim_by.date()),
        "inProgress": audit.in_progress,
        "worstService": audit.worst_component,
        "incidents": [{"name": i.name, "start": i.started_at.isoformat(), "minutes": i.minutes_in_window, "impact": i.impact, "url": i.url} for i in counted[:8]],
    }


def template_claim(audit: Audit, lessons: list[str], company: str) -> Email:
    counted = [i for i in audit.incidents if i.counted]
    lines = [
        f"Hi {audit.vendor_name} team,",
        "",
        f"We're requesting a service credit for {audit.promise.service} for {audit.window_start:%B %d} to {audit.window_end:%B %d, %Y}.",
        f"Your SLA ({audit.promise.source.title}) promises {audit.rule_text}.",
        f"Your public status page shows {audit.downtime_minutes:g} minutes of outage in that period, for {audit.uptime_pct:.3f}% uptime:",
    ]
    for inc in counted[:8]:
        lines.append(f"- {inc.started_at:%b %d %H:%M} UTC, {inc.minutes_in_window:g} min, {inc.name} ({inc.url})")
    lines += [
        "",
        f"That puts the credit at {audit.credit_pct:g}% of {audit.fee_in_window_usd:,.2f} USD, so {audit.owed_usd:,.2f} USD.",
        *(["The period isn't over yet, so this is the minimum: downtime so far already breaks the promise."] if audit.in_progress else []),
        "Please apply it to our next invoice and confirm by reply.",
    ]
    if lessons:
        lines += ["", "For your review: every incident above links to your own status page with its start and resolve times."]
    lines += ["", "Thanks,", company]
    return Email(subject=f"Service credit request: {audit.promise.service}, {audit.window_start:%b %Y}", body="\n".join(lines))
