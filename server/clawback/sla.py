"""The money math: which incidents count, how much downtime that is, the uptime %, the credit and the
amount owed. Pure functions with no network, so tests/test_sla.py can pin every number the demo shows.

Honest limits (say these out loud if a judge asks):
- Vendors measure downtime with their own monitoring. A public status page is the best evidence a
  customer has, so this is an estimate of what to claim, not the vendor's final number.
- Only "major" and "critical" incidents on covered components count by default. "minor" is opt-in.
- Overlapping incidents are merged so the same minute is never counted twice.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import CreditRule, Incident, Vendor, Window

COUNTED_IMPACTS = {"major", "critical"}


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def window_bounds(window: Window, start: datetime | None = None, now: datetime | None = None, period: str = "last") -> tuple[datetime, datetime]:
    """The audited window. With no start: the current month/quarter (period="current") or the last full one."""
    now = _utc(now or datetime.now(timezone.utc))
    if start is None and period == "current":
        start = now
    if start is None:
        if window == "month":
            first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start = (first_this - timedelta(days=1)).replace(day=1)
        else:
            q_month = 3 * ((now.month - 1) // 3) + 1
            first_this_q = now.replace(month=q_month, day=1, hour=0, minute=0, second=0, microsecond=0)
            prev = first_this_q - timedelta(days=1)
            start = prev.replace(month=3 * ((prev.month - 1) // 3) + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    start = _utc(start).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if window == "quarter":
        start = start.replace(month=3 * ((start.month - 1) // 3) + 1)
    months = 1 if window == "month" else 3
    y, m = start.year, start.month + months
    while m > 12:
        y, m = y + 1, m - 12
    end = start.replace(year=y, month=m, day=1)
    return start, end


def window_minutes(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 60.0


def is_covered(incident: Incident, vendor: Vendor) -> bool:
    if not vendor.covered_components:
        return True
    if not incident.components:
        # Statuspage incidents without components still describe an outage; count them only by name match.
        name = incident.name.lower()
        return any(c.lower() in name for c in vendor.covered_components)
    wanted = [c.lower() for c in vendor.covered_components]
    return any(any(w in comp.lower() for w in wanted) for comp in incident.components)


def classify(incidents: list[Incident], vendor: Vendor, start: datetime, end: datetime, count_minor: bool = False, now: datetime | None = None) -> list[Incident]:
    """Marks each incident counted or not, with the reason, and clips its minutes to the window."""
    now = _utc(now or datetime.now(timezone.utc))
    impacts = COUNTED_IMPACTS | ({"minor"} if count_minor else set())
    out: list[Incident] = []
    for inc in incidents:
        s = _utc(inc.started_at)
        e = _utc(inc.resolved_at) if inc.resolved_at else now
        clip_s, clip_e = max(s, start), min(e, end)
        inside = max(0.0, (clip_e - clip_s).total_seconds() / 60.0)
        item = inc.model_copy(update={"minutes_in_window": round(inside, 1)})
        if inside <= 0:
            item.counted, item.reason = False, "outside the audited window"
        elif inc.impact not in impacts:
            item.counted, item.reason = False, f"impact was {inc.impact}, not an outage"
        elif not is_covered(inc, vendor):
            item.counted, item.reason = False, "component not covered by the promise"
        else:
            item.counted, item.reason = True, f"{inc.impact} outage on a covered service"
        out.append(item)
    return out


def downtime_minutes(incidents: list[Incident], start: datetime, end: datetime, now: datetime | None = None) -> float:
    """Union of counted incident intervals inside the window, so overlaps count once."""
    now = _utc(now or datetime.now(timezone.utc))
    spans: list[tuple[datetime, datetime]] = []
    for inc in incidents:
        if not inc.counted:
            continue
        s = max(_utc(inc.started_at), start)
        e = min(_utc(inc.resolved_at) if inc.resolved_at else now, end)
        if e > s:
            spans.append((s, e))
    spans.sort()
    total = 0.0
    cur_s: datetime | None = None
    cur_e: datetime | None = None
    for s, e in spans:
        if cur_e is None or s > cur_e:
            if cur_e is not None and cur_s is not None:
                total += (cur_e - cur_s).total_seconds()
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None and cur_s is not None:
        total += (cur_e - cur_s).total_seconds()
    return round(total / 60.0, 1)


def uptime_pct(down: float, minutes: float) -> float:
    if minutes <= 0:
        return 100.0
    return round(100.0 * (minutes - down) / minutes, 4)


def credit_pct(rule: CreditRule, uptime: float, down: float, minutes: float, affected_ratio: float = 1.0) -> float:
    if rule.type == "tiered":
        best = 0.0
        for tier in rule.tiers:
            hit = uptime <= tier.threshold if tier.inclusive else uptime < tier.threshold
            if hit:
                best = max(best, tier.credit_pct)
        return min(best, rule.cap_pct)
    # proportional (Cloudflare style): multiplier x outage minutes x affected share / scheduled minutes
    if minutes <= 0 or down <= 0:
        return 0.0
    pct = rule.multiplier * down * max(0.0, min(1.0, affected_ratio)) / minutes * 100.0
    return round(min(pct, rule.cap_pct), 4)


def fee_in_window(monthly_fee: float, window: Window) -> float:
    return monthly_fee * (1 if window == "month" else 3)


def rule_text(vendor: Vendor) -> str:
    p = vendor.promise
    period = "a month" if p.window == "month" else "a quarter"
    if p.rule.type == "tiered":
        parts = []
        for t in sorted(p.rule.tiers, key=lambda t: -t.threshold):
            sign = "at or below" if t.inclusive else "below"
            parts.append(f"{t.credit_pct:g}% back {sign} {t.threshold:g}%")
        return f"{p.target_pct:g}% uptime {period}, or " + ", ".join(parts)
    return f"{p.target_pct:g}% uptime {period}, or {p.rule.multiplier:g}x the fee for the share of time it was down"


def downtime_by_component(incidents: list[Incident], vendor: Vendor, start: datetime, end: datetime, now: datetime | None = None) -> dict[str, float]:
    """Per covered service, for vendors that measure each service on its own (GitHub's Service Features)."""
    out: dict[str, float] = {}
    for comp in vendor.covered_components:
        mine = [i for i in incidents if i.counted and any(comp.lower() in c.lower() for c in i.components)]
        out[comp] = downtime_minutes(mine, start, end, now)
    return out
