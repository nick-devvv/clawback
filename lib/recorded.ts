// A recorded run of the whole demo, written by `npm run record` (scripts/record_demo.py) against a running API.
// Replayed by lib/api.ts when the API is unreachable. Re-record after Cognee + Claude are connected.

import type { Audit, Briefing, Claim, Health, MemoryEvent, PermissionRow, SkillProposal, TeamReport, Vendor } from "./types";
import data from "../data/demo/recorded.json";

export interface Recorded {
  health: Health;
  vendors: Vendor[];
  team: TeamReport;
  permissions: PermissionRow[];
  seed: MemoryEvent[];
  audits: Record<string, Audit>;
  draft: Claim;
  sent: Claim;
  contested: Claim;
  resolved: Claim;
  proposal: SkillProposal;
  paid: Claim;
  handoff: Briefing;
  memory: MemoryEvent[];
}

export const RECORDED = data as unknown as Recorded;
