// The API contract, mirrored from server/clawback/models.py (JSON is camelCase).
// If a field changes there, change it here in the same PR. Full contract: docs/API.md.

export type Window = "month" | "quarter";
export type Impact = "none" | "minor" | "major" | "critical" | "maintenance";
export type ClaimStatus = "draft" | "sent" | "contested" | "accepted" | "paid";
export type MemoryOp = "remember" | "recall" | "improve" | "forget" | "entry" | "conflicts" | "resolve" | "health";

export interface Source {
  title: string;
  url: string;
  quote: string;
  kind: "sla" | "email" | "status_page" | "vendor_reply" | "human";
  date: string;
}

export interface CreditTier { threshold: number; inclusive: boolean; creditPct: number }
export interface CreditRule { type: "tiered" | "proportional"; tiers: CreditTier[]; multiplier: number; capPct: number }

export interface VendorPromise {
  id: string;
  vendorId: string;
  service: string;
  targetPct: number;
  window: Window;
  rule: CreditRule;
  feeBasis: string;
  claimDeadlineDays: number;
  claimHow: string;
  source: Source;
  origin: "sla" | "email";
  confidence: number;
}

export interface Vendor {
  id: string;
  name: string;
  statusPage: string;
  coveredComponents: string[];
  plan: string;
  monthlyFeeUsd: number;
  promise: VendorPromise;
}

export interface Incident {
  id: string;
  name: string;
  impact: Impact;
  startedAt: string;
  resolvedAt: string | null;
  minutes: number;
  minutesInWindow: number;
  components: string[];
  url: string;
  status: string;
  counted: boolean;
  reason: string;
}

export interface Audit {
  id: string;
  vendorId: string;
  vendorName: string;
  window: Window;
  windowStart: string;
  windowEnd: string;
  windowMinutes: number;
  downtimeMinutes: number;
  uptimePct: number;
  targetPct: number;
  breached: boolean;
  creditPct: number;
  feeInWindowUsd: number;
  owedUsd: number;
  claimBy: string;
  ruleText: string;
  promise: VendorPromise;
  incidents: Incident[];
  statusSource: "live" | "snapshot" | "none";
  inProgress: boolean;
  worstComponent: string;
  byComponent: Record<string, number>;
  computedAt: string;
}

export interface Email { subject: string; body: string; to: string }
export interface ConflictFact { id: string; text: string; source: Source }
export interface Conflict {
  id: string;
  question: string;
  facts: ConflictFact[];
  status: "unresolved" | "resolved";
  selectedFactId: string | null;
  reason: string;
  fromCognee: boolean;
}

export interface Claim {
  id: string;
  vendorId: string;
  audit: Audit;
  status: ClaimStatus;
  email: Email;
  evidence: Source[];
  conflict: Conflict | null;
  lessons: string[];
  memoryDataIds: string[];
  sessionId: string;
  createdAt: string;
  updatedAt: string;
}

export interface MemoryEvent {
  id: string;
  at: string;
  op: MemoryOp;
  target: "cognee" | "offline";
  dataset: string;
  sessionId: string | null;
  summary: string;
  ms: number;
  ok: boolean;
  detail: Record<string, unknown>;
}

export interface Health {
  ok: boolean;
  mode: "live" | "demo";
  cognee: "connected" | "unreachable" | "off";
  cogneeUrl: string;
  llm: "claude" | "off";
  store: "redis" | "memory";
  statusPages: "live" | "snapshot";
  vendors: number;
}

export interface AskResult { answer: string; references: Source[]; memory: MemoryEvent[] }
export interface Briefing { agentId: string; recalledFrom: "cognee" | "offline"; summary: string; openClaims: string[]; lessons: string[]; memory: MemoryEvent[] }

// The Cognee track: shared memory across agents, permissions, skill self-improvement.
export type AgentName = "auditor" | "claims-writer" | "inbox-assistant";
export interface TeamReport {
  target: "cognee" | "offline";
  datasets: Record<string, string>;
  agents: Record<AgentName, { id?: string; error?: string }>;
  grants: string[];
  skill: string | null;
}
// deniedBy: who refused. allowed:false with deniedBy:null is an error (timeout, missing key), not a refusal.
export interface PermissionRow { agent: AgentName; dataset: string; allowed: boolean; deniedBy: "cognee" | "offline" | null; summary: string }
export interface SkillProposal { proposalId?: string; offline?: boolean; error?: string; [k: string]: unknown }
