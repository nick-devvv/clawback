"use client";

// Starter screen: the whole demo flow on one page, wired to the real API (lib/api.ts), with the
// recorded run as a fallback. It works end to end so the backend can be tested from day one.
// Nick: this is plumbing, not the design. Split it into the screens in docs/FRONTEND.md and restyle.

import { useEffect, useState } from "react";
import { api, isReplaying } from "@/lib/api";
import type { Audit, Briefing, Claim, Health, MemoryEvent, PermissionRow, Vendor } from "@/lib/types";
import { Crab } from "../_ui/Crab";
import { MemoryTape } from "../_ui/MemoryTape";
import { Receipt } from "../_ui/Receipt";

const PUSHBACK =
  "Thanks for reaching out. Our records show only 45 minutes of qualifying downtime for GitHub Actions this quarter, because we only count periods where the error rate stayed above 5% for the whole minute.";

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [audits, setAudits] = useState<Record<string, Audit>>({});
  const [claim, setClaim] = useState<Claim | null>(null);
  const [brief, setBrief] = useState<Briefing | null>(null);
  const [tape, setTape] = useState<MemoryEvent[]>([]);
  const [busy, setBusy] = useState<string>("");
  const [perms, setPerms] = useState<PermissionRow[]>([]);

  const refreshTape = async () => setTape(await api.memory());

  useEffect(() => {
    api.health().then(setHealth);
    api.vendors().then(setVendors);
    refreshTape();
  }, []);

  async function step(label: string, fn: () => Promise<void>) {
    setBusy(label);
    try {
      await fn();
    } finally {
      setBusy("");
      refreshTape();
    }
  }

  const github = audits.github;

  return (
    <main style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 420px", gap: 32, padding: "40px 48px", maxWidth: 1320, margin: "0 auto" }}>
      <section style={{ display: "flex", flexDirection: "column", gap: 28 }}>
        <header style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <Crab mood={claim?.status === "paid" ? "happy" : claim ? "grab" : "idle"} />
          <div>
            <h1 className="serif" style={{ fontSize: 64, lineHeight: 1, margin: 0 }}>you&apos;re owed.</h1>
            <p className="serif faint" style={{ fontSize: 34, margin: "4px 0 0" }}>your vendors broke their promises.</p>
          </div>
        </header>

        <p className="label">
          {health ? `cognee ${health.cognee} · claude ${health.llm} · status ${health.statusPages}` : "connecting"}
          {isReplaying() ? " · replaying recorded run" : ""}
        </p>

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <button className="pill" disabled={!!busy} onClick={() => step("reading", async () => {
            await api.seed();
            const out: Record<string, Audit> = {};
            for (const v of vendors) out[v.id] = await api.audit(v.id);
            setAudits(out);
          })}>
            {busy === "reading" ? "checking…" : "Check my vendors"}
          </button>
          <button className="ghost" disabled={!!busy} onClick={() => step("agents", async () => { await api.setupAgents(); setPerms(await api.permissions()); })}>Agents + permissions</button>
          <button className="ghost" disabled={!!busy} onClick={() => step("reset", async () => { await api.reset(); setAudits({}); setClaim(null); setBrief(null); })}>Reset</button>
        </div>

        {perms.length > 0 && (
          <div className="card arrive">
            <div className="label">shared memory · who can read what</div>
            <table className="mono" style={{ width: "100%", fontSize: 14, marginTop: 10, borderCollapse: "collapse" }}>
              <tbody>
                {["auditor", "claims-writer", "inbox-assistant"].map((a) => (
                  <tr key={a}>
                    <td style={{ padding: "6px 0" }}>{a}</td>
                    {perms.filter((p) => p.agent === a).map((p) => (
                      <td key={p.dataset} style={{ color: p.allowed ? "var(--ink)" : "var(--red)" }}>{p.dataset.replace("clawback_", "")} {p.allowed ? "✓" : "✕"}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {Object.keys(audits).length > 0 && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 16 }}>
            {Object.values(audits).map((a) => <Receipt key={a.id} audit={a} />)}
          </div>
        )}

        {github && github.owedUsd > 0 && !claim && (
          <button className="pill" disabled={!!busy} onClick={() => step("drafting", async () => setClaim(await api.draft(github.id)))}>
            {busy === "drafting" ? "writing the claim…" : `Claim ${github.owedUsd.toLocaleString("en-US", { style: "currency", currency: "USD" })} from GitHub`}
          </button>
        )}

        {claim && (
          <div className="card arrive">
            <div className="label">{claim.status}</div>
            <h3 style={{ margin: "8px 0" }}>{claim.email.subject}</h3>
            <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--sans)", fontSize: 15, lineHeight: 1.5, margin: 0 }}>{claim.email.body}</pre>
            {claim.lessons.length > 0 && <p className="muted">learned: {claim.lessons.join(" · ")}</p>}
            <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap" }}>
              {claim.status === "draft" && <button className="ghost" onClick={() => step("send", async () => setClaim(await api.send(claim.id)))}>Send</button>}
              {claim.status === "sent" && !claim.conflict && (
                <button className="ghost" onClick={() => step("reply", async () => setClaim(await api.reply(claim.id, PUSHBACK, "GitHub Support")))}>Vendor pushes back</button>
              )}
              {(claim.status === "sent" || claim.status === "accepted") && claim.conflict?.status === "resolved" && (
                <button className="ghost" onClick={() => step("paid", async () => setClaim(await api.paid(claim.id)))}>Mark paid</button>
              )}
            </div>
          </div>
        )}

        {claim?.conflict && claim.conflict.status === "unresolved" && (
          <div className="card arrive" style={{ boxShadow: "inset 0 0 0 1.5px var(--red)" }}>
            <div className="label" style={{ color: "var(--red)" }}>contested{claim.conflict.fromCognee ? " · found by cognee" : ""}</div>
            <h3 style={{ margin: "8px 0 14px" }}>{claim.conflict.question}</h3>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              {claim.conflict.facts.map((f) => (
                <button key={f.id} className="card" style={{ textAlign: "left", cursor: "pointer", border: 0 }}
                  onClick={() => step("resolve", async () => setClaim(await api.resolve(claim.id, f.id, f.source.kind === "status_page" ? "Their own status page shows longer" : "Vendor's number accepted")))}>
                  <div className="label">{f.source.title}</div>
                  <p style={{ margin: "8px 0 0", fontSize: 16 }}>{f.text}</p>
                </button>
              ))}
            </div>
          </div>
        )}

        {claim?.status === "paid" && (
          <button className="pill" onClick={() => step("handoff", async () => setBrief(await api.handoff()))}>Kill the agent. Start a new one.</button>
        )}

        {brief && (
          <div className="card arrive">
            <div className="label">new agent {brief.agentId} · recalled from {brief.recalledFrom}</div>
            <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--sans)", fontSize: 15 }}>{brief.summary}</pre>
            {brief.lessons.length > 0 && <p className="muted">lessons: {brief.lessons.join(" · ")}</p>}
          </div>
        )}
      </section>

      <aside style={{ position: "sticky", top: 40, alignSelf: "start" }}>
        <MemoryTape events={tape} />
      </aside>
    </main>
  );
}
