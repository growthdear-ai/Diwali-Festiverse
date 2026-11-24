"use client";

import { useRef } from "react";
import { cn } from "@/lib/utils";

/**
 * Pointer-driven 3D tilt with a soft glare. Pure CSS transforms (see .tilt-3d in globals.css).
 * Disabled for touch and reduced-motion users. Children can use .depth-1/2/3 for parallax layers.
 */
export function Tilt3D({ children, max = 6, glare = true, className }: { children: React.ReactNode; max?: number; glare?: boolean; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);

  function move(e: React.PointerEvent<HTMLDivElement>) {
    if (e.pointerType !== "mouse") return;
    const el = ref.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width;
    const py = (e.clientY - r.top) / r.height;
    el.style.setProperty("--ry", `${((px - 0.5) * 2 * max).toFixed(2)}deg`);
    el.style.setProperty("--rx", `${((0.5 - py) * 2 * max).toFixed(2)}deg`);
    el.style.setProperty("--gx", `${(px * 100).toFixed(1)}%`);
    el.style.setProperty("--gy", `${(py * 100).toFixed(1)}%`);
    el.dataset.active = "true";
  }

  function leave() {
    const el = ref.current;
    if (!el) return;
    el.style.setProperty("--rx", "0deg");
    el.style.setProperty("--ry", "0deg");
    el.dataset.active = "false";
  }

  return (
    <div className={cn("scene-3d", className)}>
      <div ref={ref} onPointerMove={move} onPointerLeave={leave} className="tilt-3d relative rounded-[inherit]">
        {children}
        {glare && <span className="tilt-glare" aria-hidden />}
      </div>
    </div>
  );
}
