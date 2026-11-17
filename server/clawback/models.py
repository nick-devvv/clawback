"""The data model. These shapes are the API contract in docs/API.md: JSON goes out in camelCase,
and requests may use camelCase or snake_case. Change a field here and in lib/types.ts together."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


Window = Literal["month", "quarter"]
Impact = Literal["none", "minor", "major", "critical", "maintenance"]
ClaimStatus = Literal["draft", "sent", "contested", "accepted", "paid"]
MemoryOp = Literal["remember", "recall", "improve", "forget", "entry", "conflicts", "resolve", "health"]
MemoryTarget = Literal["cognee", "offline"]


class Source(Model):
    """Where a fact came from. Every promise, incident and claim line keeps one."""

    title: str
    url: str = ""
    quote: str = ""  # a short excerpt (under 15 words); paraphrase the rest
    kind: Literal["sla", "email", "status_page", "vendor_reply", "human"] = "sla"
    date: str = ""


class CreditTier(Model):
    """Uptime at or below (inclusive) / strictly below `threshold` earns `credit_pct` of the fee."""

    threshold: float
    inclusive: bool = False
    credit_pct: float


class CreditRule(Model):
    type: Literal["tiered", "proportional"]
    tiers: list[CreditTier] = Field(default_factory=list)  # tiered: most severe tier that applies wins
    multiplier: float = 1.0  # proportional: credit % = multiplier x downtime / window minutes x 100
    cap_pct: float = 100.0


class VendorPromise(Model):
    """One promise a vendor made: the uptime target, the credit rule and how to claim."""

    id: str
    vendor_id: str
    service: str
    target_pct: float
    window: Window
    rule: CreditRule
    fee_basis: str  # plain words: which fees the credit is a share of
    claim_deadline_days: int
    claim_how: str
    source: Source
    origin: Literal["sla", "email"] = "sla"
    confidence: float = 1.0


class Vendor(Model):
    id: str
    name: str
    status_page: str  # base URL of an Atlassian Statuspage, e.g. https://www.githubstatus.com
    covered_components: list[str] = Field(default_factory=list)  # empty = every component counts
    plan: str
    monthly_fee_usd: float
    promise: VendorPromise


class Incident(Model):
    id: str
    name: str
    impact: Impact
    started_at: datetime
    resolved_at: datetime | None
    minutes: float  # full length of the incident
    minutes_in_window: float = 0.0  # the part that falls inside the audited window
    components: list[str] = Field(default_factory=list)
    url: str = ""
    status: str = ""  # Statuspage status: investigating, identified, monitoring, resolved, postmortem
    counted: bool = False  # true when it counts as downtime under the vendor's promise
    reason: str = ""  # why it was or wasn't counted, in plain words


class AuditRequest(Model):
    vendor_id: str
    period: Literal["current", "last"] = "current"  # the month/quarter we're in now, or the last full one
    window_start: datetime | None = None  # overrides `period` with an explicit window start
    monthly_fee_usd: float | None = None  # overrides the vendor default
    affected_ratio: float = 1.0  # share of your traffic hit, for proportional rules
    count_minor: bool = False  # count "minor" incidents as downtime too


class Audit(Model):
    id: str
    vendor_id: str
    vendor_name: str
    window: Window
    window_start: datetime
    window_end: datetime
    window_minutes: float
    downtime_minutes: float
    uptime_pct: float
    target_pct: float
    breached: bool
    credit_pct: float
    fee_in_window_usd: float
    owed_usd: float
    claim_by: datetime
    rule_text: str
    promise: VendorPromise
    incidents: list[Incident]
    status_source: Literal["live", "snapshot", "none"]
    in_progress: bool = False  # window not over yet: uptime is the best case so far, it can only drop
    worst_component: str = ""  # per-service vendors (GitHub): the service that missed by the most
    by_component: dict[str, float] = Field(default_factory=dict)  # downtime minutes per covered service
    computed_at: datetime


class Email(Model):
    subject: str
    body: str
    to: str = ""


class ConflictFact(Model):
    id: str
    text: str
    source: Source


class Conflict(Model):
    id: str
    question: str
    facts: list[ConflictFact]
    status: Literal["unresolved", "resolved"] = "unresolved"
    selected_fact_id: str | None = None
    reason: str = ""
    from_cognee: bool = False  # true when Cognee's own conflict review found it


class Claim(Model):
    id: str
    vendor_id: str
    audit: Audit
    status: ClaimStatus
    email: Email
    evidence: list[Source]
    conflict: Conflict | None = None
    lessons: list[str] = Field(default_factory=list)  # what the agent learned about this vendor
    memory_data_ids: list[str] = Field(default_factory=list)  # Cognee data ids, so `forget` can remove them
    session_id: str
    created_at: datetime
    updated_at: datetime


class MemoryEvent(Model):
    """One call to Cognee, shown live in the UI's memory tape."""

    id: str
    at: datetime
    op: MemoryOp
    target: MemoryTarget
    dataset: str
    session_id: str | None = None
    summary: str
    ms: int
    ok: bool
    detail: dict = Field(default_factory=dict)


# ----- request bodies -----


class IngestRequest(Model):
    vendor_id: str
    kind: Literal["sla", "email", "contract"] = "email"
    title: str = "Pasted text"
    text: str
    date: str = ""


class IngestResult(Model):
    vendor_id: str
    promises: list[VendorPromise]
    memory: list[MemoryEvent]


class DraftRequest(Model):
    audit_id: str


class ReplyRequest(Model):
    text: str
    sender: str = "vendor support"


class ResolveRequest(Model):
    selected_fact_id: str
    reason: str = ""


class AskRequest(Model):
    question: str
    session_id: str | None = None


class AskResult(Model):
    answer: str
    references: list[Source]
    memory: list[MemoryEvent]


class Briefing(Model):
    """What a brand-new agent knows after the old one is killed, read back from memory only."""

    agent_id: str
    recalled_from: MemoryTarget
    summary: str
    open_claims: list[str]
    lessons: list[str]
    memory: list[MemoryEvent]


class Health(Model):
    ok: bool
    mode: Literal["live", "demo"]
    cognee: Literal["connected", "unreachable", "off"]
    cognee_url: str
    llm: Literal["claude", "off"]
    store: Literal["redis", "memory"]
    status_pages: Literal["live", "snapshot"]
    vendors: int


class PermissionRow(Model):
    """One cell of GET /agents/permissions. deniedBy None with allowed False means an error, not a refusal."""

    agent: str
    dataset: str
    allowed: bool
    denied_by: Literal["cognee", "offline"] | None = None
    summary: str
