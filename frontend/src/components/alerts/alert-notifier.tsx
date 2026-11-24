"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";

function chime() {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(1320, ctx.currentTime + 0.12);
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.15, ctx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.35);
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.4);
    osc.onended = () => ctx.close();
  } catch {}
}

/** Polls alerts while the app is open; surfaces new ones as toast, sound and browser notification. */
export function AlertNotifier() {
  const { prefs } = usePrefs();
  const router = useRouter();
  const seen = useRef<Set<number> | null>(null);
  const prefsRef = useRef(prefs);
  useEffect(() => {
    prefsRef.current = prefs;
  });

  useEffect(() => {
    let live = true;
    const check = async () => {
      try {
        const alerts = await api.alerts.list();
        if (!live) return;
        if (!seen.current) {
          seen.current = new Set(alerts.map((a) => a.id)); // baseline: don't notify for history
          return;
        }
        for (const a of alerts) {
          if (seen.current.has(a.id)) continue;
          seen.current.add(a.id);
          const p = prefsRef.current;
          toast(`@Nazar: ${a.title}`, {
            description: a.observed_value ?? undefined,
            action: { label: "View", onClick: () => router.push(`/alerts/${a.id}`) },
          });
          if (p.alertSound) chime();
          if (p.browserNotifications && typeof Notification !== "undefined" && Notification.permission === "granted" && document.hidden) {
            const n = new Notification(`Nazar Rakho: ${a.title}`, { body: a.observed_value ?? "", tag: `alert-${a.id}` });
            n.onclick = () => {
              window.focus();
              router.push(`/alerts/${a.id}`);
            };
          }
        }
      } catch {}
    };
    check();
    const t = setInterval(check, 45_000);
    return () => {
      live = false;
      clearInterval(t);
    };
  }, [router]);

  return null;
}
