// Browser-side calls to the Clawback API (docs/API.md). Every call falls back to the recorded run in
// data/demo/recorded.json when the API can't be reached, so the demo never dies on stage.
// NEXT_PUBLIC_DEMO=1 skips the network entirely.

import type { AskResult, Audit, Briefing, Claim, Health, MemoryEvent, PermissionRow, SkillProposal, TeamReport, Vendor } from "./types";
import { RECORDED } from "./recorded";

const BASE = (process.env.NEXT_PUBLIC_API_BASE || "").replace(/\/$/, "") + "/api/py";
const FORCE_DEMO = process.env.NEXT_PUBLIC_DEMO === "1";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let replaying = FORCE_DEMO;
export const isReplaying = () => replaying;

async function call<T>(path: string, init: RequestInit | undefined, fallback: () => T): Promise<T> {
  if (replaying) return fallback();
  try {
    const res = await fetch(BASE + path, {
      ...init,
      headers: { "content-type": "application/json", ...(init?.headers || {}) },
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new ApiError(res.status, body?.detail?.message || `Request failed (${res.status})`);
    }
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof ApiError && err.status < 500) throw err; // a real "no", not an outage
    replaying = true; // API is down: switch to the recorded run for the rest of the session
    return fallback();
  }
}

const post = (body?: unknown): RequestInit => ({ method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  health: () => call<Health>("/health", undefined, () => RECORDED.health),
  vendors: () => call<Vendor[]>("/vendors", undefined, () => RECORDED.vendors),
  seed: () => call<MemoryEvent[]>("/seed", post(), () => RECORDED.seed),
  audit: (vendorId: string, monthlyFeeUsd?: number) =>
    call<Audit>("/audit", post({ vendorId, monthlyFeeUsd }), () => RECORDED.audits[vendorId] ?? RECORDED.audits.github),
  draft: (auditId: string) => call<Claim>("/claims", post({ auditId }), () => RECORDED.draft),
  send: (claimId: string) => call<Claim>(`/claims/${claimId}/send`, post(), () => RECORDED.sent),
  reply: (claimId: string, text: string, sender = "vendor support") =>
    call<Claim>(`/claims/${claimId}/reply`, post({ text, sender }), () => RECORDED.contested),
  resolve: (claimId: string, selectedFactId: string, reason = "") =>
    call<Claim>(`/claims/${claimId}/resolve`, post({ selectedFactId, reason }), () => RECORDED.resolved),
  paid: (claimId: string) => call<Claim>(`/claims/${claimId}/paid`, post(), () => RECORDED.paid),
  ask: (question: string) => call<AskResult>("/ask", post({ question }), () => ({ answer: RECORDED.handoff.summary, references: [], memory: [] })),
  handoff: () => call<Briefing>("/handoff", post(), () => RECORDED.handoff),
  memory: () => call<MemoryEvent[]>("/memory", undefined, () => RECORDED.memory),
  setupAgents: () => call<TeamReport>("/agents/setup", post(), () => RECORDED.team),
  permissions: () => call<PermissionRow[]>("/agents/permissions", undefined, () => RECORDED.permissions),
  proposal: (claimId: string) => call<SkillProposal>(`/claims/${claimId}/proposal`, undefined, () => RECORDED.proposal),
  applyProposal: (claimId: string) => call<{ ok: boolean }>(`/claims/${claimId}/proposal/apply`, post(), () => ({ ok: true })),
  reset: () => call<{ ok: boolean }>("/reset", post(), () => ({ ok: true })),
};
