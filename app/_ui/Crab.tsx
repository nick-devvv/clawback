// Clawdia, the pixel crab. Text grid -> SVG rects, crisp edges (same trick as Boneify's Rex and picky's mascot).
// k = ink outline, o = shell (accent), w = eye white, r = receipt. Moods are different grids.

const IDLE = [
  "..kk..........kk..",
  ".kook........kook.",
  ".koook......kooko.",
  "..kook......kook..",
  "...kk..kkkk..kk...",
  "......koooook.....",
  "..kk.kowkkwok.kk..",
  ".kook.koooook.kook",
  "..kkkkoooooookkkk.",
  "....kooooooook....",
  "...k.kk.kk.kk.k...",
];
const HAPPY = IDLE.map((r, i) => (i === 6 ? "..kk.kokwwkok.kk.." : r));
const GRAB = IDLE.map((r, i) => (i === 1 ? ".kook...rr...kook." : i === 2 ? ".koook..rr..kooko." : r));

const GRIDS = { idle: IDLE, happy: HAPPY, grab: GRAB } as const;
const FILL: Record<string, string> = { k: "#22170F", o: "#FF6A1F", w: "#FFFAF2", r: "#FFFAF2" };

export function Crab({ mood = "idle", width = 72 }: { mood?: keyof typeof GRIDS; width?: number }) {
  const rows = GRIDS[mood];
  const paths: Record<string, string> = {};
  rows.forEach((row, y) => {
    [...row].forEach((c, x) => {
      if (c !== ".") paths[c] = (paths[c] || "") + `M${x} ${y}h1v1h-1z`;
    });
  });
  const w = rows[0].length;
  return (
    <svg width={width} height={(width * rows.length) / w} viewBox={`0 0 ${w} ${rows.length}`} shapeRendering="crispEdges" aria-hidden="true">
      {Object.entries(paths).map(([c, d]) => (
        <path key={c} d={d} fill={FILL[c]} />
      ))}
    </svg>
  );
}
