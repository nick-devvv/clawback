"""The money math, pinned. Run: python -m pytest -q"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from clawback import sla  # noqa: E402
from clawback.models import CreditRule, CreditTier  # noqa: E402
from clawback.statuspage import parse_incidents  # noqa: E402
from clawback.vendors import get_vendor  # noqa: E402

UTC = timezone.utc


def payload(*rows):
    return {"incidents": [dict(r) for r in rows]}


def inc(id, start, end, impact="major", comps=("Actions",), status="resolved"):
    return {
        "id": id,
        "name": f"Incident {id}",
        "impact": impact,
        "status": status,
        "created_at": start,
        "started_at": start,
        "resolved_at": end,
        "shortlink": f"https://stspg.io/{id}",
        "components": [{"name": c} for c in comps],
        "incident_updates": [{"created_at": end or start}],
    }


def test_window_bounds_month_and_quarter():
    now = datetime(2026, 11, 16, 12, tzinfo=UTC)
    assert sla.window_bounds("month", now=now, period="current") == (datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 12, 1, tzinfo=UTC))
    assert sla.window_bounds("month", now=now, period="last") == (datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC))
    assert sla.window_bounds("quarter", now=now, period="current") == (datetime(2026, 10, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC))
    assert sla.window_bounds("quarter", now=now, period="last") == (datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC))


def test_overlaps_count_once_and_minor_is_skipped():
    github = get_vendor("github")
    start, end = datetime(2026, 10, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC)
    rows = parse_incidents(
        payload(
            inc("a", "2026-10-05T10:00:00Z", "2026-10-05T11:00:00Z"),  # 60 min
            inc("b", "2026-10-05T10:30:00Z", "2026-10-05T11:30:00Z"),  # overlaps a by 30 -> +30
            inc("c", "2026-10-06T10:00:00Z", "2026-10-06T12:00:00Z", impact="minor"),  # not counted
            inc("d", "2026-10-07T10:00:00Z", "2026-10-07T10:45:00Z", comps=("Copilot",)),  # not covered
        )
    )
    rows = sla.classify(rows, github, start, end, now=datetime(2026, 11, 16, tzinfo=UTC))
    counted = {r.id: r.counted for r in rows}
    assert counted == {"a": True, "b": True, "c": False, "d": False}
    assert sla.downtime_minutes(rows, start, end) == 90.0
    assert sla.downtime_by_component(rows, github, start, end)["Actions"] == 90.0


def test_resolved_without_resolved_at_uses_last_update():
    rows = parse_incidents(payload(inc("x", "2026-10-05T10:00:00Z", None) | {"incident_updates": [{"created_at": "2026-10-05T10:20:00Z"}]}))
    assert rows[0].minutes == 20.0


def test_github_tiers():
    rule = get_vendor("github").promise.rule
    assert sla.credit_pct(rule, 99.95, 0, 1) == 0
    assert sla.credit_pct(rule, 99.9, 0, 1) == 10  # "99.9% or less" is inclusive
    assert sla.credit_pct(rule, 99.5, 0, 1) == 10
    assert sla.credit_pct(rule, 98.9, 0, 1) == 25


def test_twilio_tier_is_strict():
    rule = get_vendor("twilio").promise.rule
    assert sla.credit_pct(rule, 99.95, 0, 1) == 0
    assert sla.credit_pct(rule, 99.94, 0, 1) == 10


def test_cloudflare_proportional():
    rule = get_vendor("cloudflare").promise.rule
    # 180 minutes out of a 30-day month (43,200 minutes), everyone affected: 0.4167% of the fee
    assert round(sla.credit_pct(rule, 0, 180, 43200, 1.0), 4) == 0.4167
    assert round(sla.credit_pct(rule, 0, 180, 43200, 0.5), 4) == 0.2083


def test_tiered_picks_most_severe():
    rule = CreditRule(type="tiered", tiers=[CreditTier(threshold=99.9, inclusive=True, credit_pct=10), CreditTier(threshold=99.0, credit_pct=25)])
    assert sla.credit_pct(rule, 95.0, 0, 1) == 25
