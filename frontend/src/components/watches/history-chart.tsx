"use client";

import { useState } from "react";
import { dateTime, toDate } from "@/lib/format";
import type { Observation } from "@/lib/types";

/** Line chart of numeric observations with an optional target line. Renders only real points. */
export function HistoryChart({ points, target, format }: { points: Observation[]; target?: number | null; format: (v: number) => string }) {
  const data = points
    .filter((p) => typeof p.observed_value === "number" && toDate(p.checked_at))
    .map((p) => ({ v: p.observed_value as number, t: toDate(p.checked_at)!.getTime(), at: p.checked_at }))
    .sort((a, b) => a.t - b.t);
  const [hover, setHover] = useState<number | null>(null);

  if (data.length < 2) return <p className="py-10 text-center text-sm text-muted-foreground">The chart appears after Nazar has made at least two checks.</p>;

  const W = 640;
  const H = 220;
  const pad = { l: 8, r: 8, t: 16, b: 24 };
  const values = data.map((d) => d.v).concat(target ? [target] : []);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (i: number) => pad.l + (i / (data.length - 1)) * (W - pad.l - pad.r);
  const y = (v: number) => pad.t + (1 - (v - min) / span) * (H - pad.t - pad.b);
  const line = data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d.v).toFixed(1)}`).join(" ");
  const area = `${line} L${x(data.length - 1)},${H - pad.b} L${x(0)},${H - pad.b} Z`;
  const h = hover !== null ? data[hover] : data.at(-1)!;

  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <p className="tabular-nums text-xl font-semibold">{format(h.v)}</p>
        <p className="text-xs text-muted-foreground">{dateTime(h.at)}</p>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-auto w-full touch-none"
        role="img"
        aria-label={`Observed values from ${format(data[0].v)} to ${format(data.at(-1)!.v)}`}
        onPointerLeave={() => setHover(null)}
        onPointerMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const rel = ((e.clientX - rect.left) / rect.width) * W;
          setHover(Math.max(0, Math.min(data.length - 1, Math.round(((rel - pad.l) / (W - pad.l - pad.r)) * (data.length - 1)))));
        }}
      >
        <defs>
          <linearGradient id="hc-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="#047857" stopOpacity="0.14" />
            <stop offset="1" stopColor="#047857" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1={pad.l} x2={W - pad.r} y1={pad.t + f * (H - pad.t - pad.b)} y2={pad.t + f * (H - pad.t - pad.b)} stroke="rgb(15 23 42 / 0.06)" />
        ))}
        {target != null && (
          <g>
            <line x1={pad.l} x2={W - pad.r} y1={y(target)} y2={y(target)} stroke="#B45309" strokeDasharray="4 4" strokeOpacity="0.7" />
            <text x={W - pad.r} y={y(target) - 6} textAnchor="end" fontSize="11" fill="#B45309">
              Target {format(target)}
            </text>
          </g>
        )}
        <path d={area} fill="url(#hc-fill)" />
        <path d={line} fill="none" stroke="#047857" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={H - pad.b} stroke="rgb(15 23 42 / 0.2)" />}
        <circle cx={x(hover ?? data.length - 1)} cy={y(h.v)} r="4" fill="#fff" stroke="#047857" strokeWidth="2" />
        <text x={pad.l} y={H - 6} fontSize="11" fill="#94A3B8">
          {toDate(data[0].at)!.toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
        </text>
        <text x={W - pad.r} y={H - 6} fontSize="11" fill="#94A3B8" textAnchor="end">
          {toDate(data.at(-1)!.at)!.toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
        </text>
      </svg>
    </div>
  );
}
