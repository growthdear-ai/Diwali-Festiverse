"use client";

import { ArrowLeft, Bell, Pause, Pencil, Play, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { PageContainer } from "@/components/app-shell";
import { ErrorState, LoadingList, StatusBadge, WatchTypeIcon } from "@/components/common";
import { VerificationBadge } from "@/components/alerts/alert-card";
import { useRooms } from "@/components/rooms/rooms-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { HistoryChart } from "@/components/watches/history-chart";
import { ConfirmDelete, useWatchActions } from "@/components/watches/watch-card";
import { WatchDialog } from "@/components/watches/watch-dialog";
import { api } from "@/lib/api";
import { dateTime, latestValue, money, relativeTime, targetCondition, toDate, WATCH_TYPE_LABEL, watchTitle } from "@/lib/format";
import type { Watch, WatchRule } from "@/lib/types";
import { useApi } from "@/lib/use-api";

function ruleRows(rule: WatchRule): [string, string][] {
  switch (rule.watch_type) {
    case "flight":
      return [
        ["Route", `${rule.origin} → ${rule.destination}`],
        ["Travel date", rule.travel_date],
        ...(rule.return_date ? [["Return", rule.return_date] as [string, string]] : []),
        ["Condition", `${rule.condition} ${money(rule.target_price, rule.currency)}`],
        ["Passengers", String(rule.passengers)],
        ["Class", rule.travel_class?.replace("_", " ") ?? "Any"],
      ];
    case "stock":
      return [
        ["Symbol", rule.symbol],
        ["Exchange", rule.exchange ?? "Any"],
        ["Condition", targetCondition(rule)],
      ];
    case "job_notification":
      return [
        ["Keywords", rule.keywords.join(", ")],
        ...(rule.organization ? [["Organization", rule.organization] as [string, string]] : []),
        ["Official domains", rule.domains.join(", ")],
      ];
    case "topic":
      return [
        ["Watching", rule.query],
        ["Source", { web: "Web search", news: "Google News", jobs: "Job openings", shopping: "Google Shopping" }[rule.source]],
        ["Condition", targetCondition(rule)],
      ];
  }
}

function chartTarget(rule: WatchRule) {
  if (rule.watch_type === "flight") return rule.target_price;
  if (rule.watch_type === "stock") return rule.target_price ?? null;
  if (rule.watch_type === "topic") return rule.target_price ?? null;
  return null;
}

export default function WatchDetailPage() {
  const { id } = useParams<{ id: string }>();
  const watchId = Number(id);
  const router = useRouter();
  const { rooms } = useRooms();
  const watch = useApi(() => api.watches.get(watchId), [watchId], { pollMs: 60_000 });
  const alerts = useApi(() => api.alerts.list({ watch_id: watchId }), [watchId]);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const { busy, run } = useWatchActions((w) => (w ? watch.setData(w) : router.replace("/watches")));

  if (watch.error && !watch.data)
    return (
      <PageContainer>
        <ErrorState message={watch.error} onRetry={watch.reload} />
      </PageContainer>
    );
  if (!watch.data)
    return (
      <PageContainer>
        <LoadingList rows={3} />
      </PageContainer>
    );

  const w: Watch = watch.data;
  const rule = w.rule_json;
  const room = rooms.find((r) => r.id === w.room_id);
  const history = [...(w.history ?? [])].sort((a, b) => (toDate(b.checked_at)?.getTime() ?? 0) - (toDate(a.checked_at)?.getTime() ?? 0));
  const fmt = (v: number) => (rule.watch_type === "flight" || rule.watch_type === "topic" ? money(v, rule.currency) : rule.watch_type === "stock" ? `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 2 })}` : String(v));
  const watchAlerts = (alerts.data ?? []).filter((a) => a.watch_id === w.id);
  const value = latestValue(w);

  return (
    <PageContainer>
      <Link href="/watches" className="mb-4 inline-flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Watches
      </Link>

      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <WatchTypeIcon type={w.watch_type} className="size-11" />
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{watchTitle(rule)}</h1>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              {WATCH_TYPE_LABEL[w.watch_type]} · {room ? <Link href={`/chat/${room.id}`} className="hover:text-foreground">{room.name}</Link> : `Room #${w.room_id}`} <StatusBadge status={w.status} />
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {w.status === "active" && (
            <Button variant="secondary" onClick={() => run(w, "pause")} disabled={busy}>
              <Pause /> Pause
            </Button>
          )}
          {(w.status === "paused" || w.status === "failed") && (
            <Button variant="secondary" onClick={() => run(w, "resume")} disabled={busy}>
              <Play /> Resume
            </Button>
          )}
          <Button variant="secondary" onClick={() => setEditing(true)} disabled={w.status === "completed"}>
            <Pencil /> Edit
          </Button>
          <Button variant="danger" size="icon" onClick={() => setConfirmDelete(true)} aria-label="Delete watch">
            <Trash2 />
          </Button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-4">
        {[
          ["Current value", value ?? "No check yet", true],
          ["Target", targetCondition(rule), false],
          ["Last checked", relativeTime(w.last_checked_at), false],
          ["Next check", w.status === "active" ? relativeTime(w.next_check_at) : "—", false],
        ].map(([label, val, mono]) => (
          <Card key={label as string} className="p-4">
            <p className="text-[11px] text-subtle">{label}</p>
            <p className={mono ? "mt-1 tabular-nums text-xl font-semibold text-primary" : "mt-1 text-[13px] leading-snug"}>{val}</p>
          </Card>
        ))}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="min-w-0 space-y-6">
          {(rule.watch_type === "flight" || rule.watch_type === "stock" || (rule.watch_type === "topic" && rule.mode !== "new_results")) && (
            <Card>
              <CardHeader>
                <CardTitle>{rule.watch_type === "flight" ? "Fare history" : "Price movement"}</CardTitle>
              </CardHeader>
              <CardContent>
                <HistoryChart points={w.history ?? []} target={chartTarget(rule)} format={fmt} />
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Previous alerts</CardTitle>
              <span className="text-xs text-muted-foreground">{watchAlerts.length}</span>
            </CardHeader>
            <CardContent>
              {alerts.loading && !alerts.data ? (
                <LoadingList rows={1} />
              ) : watchAlerts.length === 0 ? (
                <p className="text-sm text-muted-foreground">No alerts from this watch yet.</p>
              ) : (
                <ul className="divide-y divide-border">
                  {watchAlerts.map((a) => (
                    <li key={a.id}>
                      <Link href={`/alerts/${a.id}`} className="flex items-center gap-3 py-3 hover:text-primary">
                        <Bell className="size-4 shrink-0 text-primary" />
                        <span className="min-w-0 flex-1 truncate text-sm">{a.title}</span>
                        <VerificationBadge status={a.verification_status} />
                        <span className="shrink-0 text-xs text-subtle">{relativeTime(a.created_at)}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Check history</CardTitle>
              <span className="text-xs text-muted-foreground">{history.length} checks</span>
            </CardHeader>
            <CardContent>
              {history.length === 0 ? (
                <p className="text-sm text-muted-foreground">{w.last_checked_at ? `Last checked ${dateTime(w.last_checked_at)}. Detailed history isn't available yet.` : "Nazar hasn't run a check yet."}</p>
              ) : (
                <div className="scrollbar-thin max-h-80 overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-card text-left text-[11px] text-subtle">
                      <tr>
                        <th className="pb-2 font-medium">Checked</th>
                        <th className="pb-2 text-right font-medium">Observed</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {history.map((h, i) => (
                        <tr key={h.id ?? i}>
                          <td className="py-2 text-muted-foreground">{dateTime(h.checked_at)}</td>
                          <td className="py-2 text-right tabular-nums">{h.observed_value != null ? fmt(h.observed_value) : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <Card className="h-fit">
          <CardHeader>
            <CardTitle>Configuration</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="space-y-3 text-sm">
              {[...ruleRows(rule), ["Check every", `${w.check_interval} min`], ["Created", dateTime(w.created_at)], ...(w.completed_at ? [["Completed", dateTime(w.completed_at)]] : [])].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4">
                  <dt className="shrink-0 text-subtle">{k}</dt>
                  <dd className="min-w-0 break-words text-right">{v}</dd>
                </div>
              ))}
            </dl>
          </CardContent>
        </Card>
      </div>

      <WatchDialog open={editing} onOpenChange={setEditing} rooms={rooms} watch={w} onSaved={(nw) => watch.setData(nw)} />
      <ConfirmDelete open={confirmDelete} onOpenChange={setConfirmDelete} busy={busy} onConfirm={() => run(w, "delete")} />
    </PageContainer>
  );
}
