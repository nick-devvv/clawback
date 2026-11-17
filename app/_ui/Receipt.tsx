// The audit as a receipt that prints line by line: counted incidents, total downtime, and the amount owed.
// Visual thesis: "a thermal receipt that prints what each vendor owes you." Nick owns the final look.

import type { Audit } from "@/lib/types";

const money = (n: number) => n.toLocaleString("en-US", { style: "currency", currency: "USD" });
const day = (s: string) => new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric" });

export function Receipt({ audit }: { audit: Audit }) {
  const counted = audit.incidents.filter((i) => i.counted);
  return (
    <div className="card print mono" style={{ fontSize: 14, lineHeight: 1.6, maxWidth: 460 }}>
      <div className="label">{audit.vendorName} · {day(audit.windowStart)} to {day(audit.windowEnd)}</div>
      <p className="muted" style={{ margin: "6px 0 14px" }}>{audit.ruleText}</p>
      {counted.map((i) => (
        <div key={i.id} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
          <a href={i.url} target="_blank" rel="noreferrer" style={{ textDecoration: "none" }}>{day(i.startedAt)} {i.name.slice(0, 34)}</a>
          <span>{i.minutesInWindow}m</span>
        </div>
      ))}
      <hr style={{ border: 0, borderTop: "1px dashed var(--faint)", margin: "12px 0" }} />
      <Row k={audit.worstComponent ? `downtime (${audit.worstComponent})` : "downtime"} v={`${audit.downtimeMinutes} min`} />
      <Row k="uptime" v={`${audit.uptimePct.toFixed(3)}% vs ${audit.targetPct}%`} />
      <Row k="credit" v={`${audit.creditPct}%`} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: 10 }}>
        <span className="label">owed</span>
        <span className="serif" style={{ fontSize: 44, fontFamily: "var(--serif)" }}>{money(audit.owedUsd)}</span>
      </div>
      {audit.inProgress && <p className="faint" style={{ margin: "6px 0 0" }}>so far · the period isn&apos;t over</p>}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between" }}>
      <span className="muted">{k}</span>
      <span>{v}</span>
    </div>
  );
}
