import { toDate } from "@/lib/format";
import type { Observation } from "@/lib/types";

/** Tiny trend line from real observations; renders nothing with fewer than two points. */
export function Sparkline({ points, width = 88, height = 28, className }: { points?: Observation[]; width?: number; height?: number; className?: string }) {
  const vals = (points ?? [])
    .filter((p) => typeof p.observed_value === "number")
    .sort((a, b) => (toDate(a.checked_at)?.getTime() ?? 0) - (toDate(b.checked_at)?.getTime() ?? 0))
    .map((p) => p.observed_value as number);
  if (vals.length < 2) return null;
  const min = Math.min(...vals);
  const span = Math.max(...vals) - min || 1;
  const xy = vals.map((v, i) => [(i / (vals.length - 1)) * (width - 4) + 2, height - 3 - ((v - min) / span) * (height - 6)]);
  const d = xy.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const down = vals.at(-1)! < vals[0];
  const color = down ? "#047857" : "#B45309";
  const [lx, ly] = xy.at(-1)!;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className={className} aria-hidden>
      <path d={`${d} L${lx},${height} L2,${height} Z`} fill={color} fillOpacity="0.07" />
      <path d={d} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={lx} cy={ly} r="2.2" fill="#fff" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}
