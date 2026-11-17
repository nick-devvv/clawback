// The memory tape: every Cognee call, newest first. This is the "Best Use of Cognee" proof on screen,
// so keep it visible during the demo. Colors: remember = ink, recall = accent, improve/forget = muted.

import type { MemoryEvent } from "@/lib/types";

const VERB: Record<string, string> = {
  remember: "remember", recall: "recall", improve: "improve", forget: "forget",
  entry: "remember entry", conflicts: "conflicts", resolve: "resolve", health: "health",
};

export function MemoryTape({ events }: { events: MemoryEvent[] }) {
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <div className="label" style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)" }}>
        memory · {events[0]?.target === "cognee" ? "cognee" : "offline"}
      </div>
      <ol style={{ listStyle: "none", margin: 0, padding: 0, maxHeight: 420, overflow: "auto" }}>
        {events.map((e) => (
          <li key={e.id} className="arrive" style={{ display: "grid", gridTemplateColumns: "118px 1fr 56px", gap: 10, padding: "10px 18px", borderBottom: "1px solid var(--line)", fontSize: 14 }}>
            <span className="mono" style={{ color: !e.ok ? "var(--red)" : e.op === "recall" ? "var(--accent)" : "var(--ink)" }}>{VERB[e.op]}</span>
            <span>
              <span className="faint mono" style={{ fontSize: 12 }}>{String(e.detail?.agent ?? "")} </span>
              {e.summary}
            </span>
            <span className="mono faint" style={{ textAlign: "right" }}>{e.ms}ms</span>
          </li>
        ))}
        {events.length === 0 && <li className="muted" style={{ padding: 18 }}>Nothing yet.</li>}
      </ol>
    </div>
  );
}
