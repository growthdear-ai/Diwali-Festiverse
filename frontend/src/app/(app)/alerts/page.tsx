"use client";

import { Bell, CheckCheck } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { PageContainer } from "@/components/app-shell";
import { EmptyState, ErrorState, LoadingList, PageHeader, WatchTypeIcon } from "@/components/common";
import { VerificationBadge } from "@/components/alerts/alert-card";
import { useRooms } from "@/components/rooms/rooms-context";
import { Button } from "@/components/ui/button";
import { Badge, Card } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/field";
import { api } from "@/lib/api";
import { relativeTime, toDate, WATCH_TYPE_LABEL } from "@/lib/format";
import { usePrefs } from "@/lib/prefs";
import type { WatchType } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

export default function AlertsPage() {
  const { rooms } = useRooms();
  const { isRead, update, prefs } = usePrefs();
  const alerts = useApi(() => api.alerts.list(), [], { pollMs: 60_000 });
  // Category comes from the alert's watch; fetch watches once to map watch_id → type.
  const watches = useApi(() => api.watches.list(), []);
  const [room, setRoom] = useState("all");
  const [category, setCategory] = useState<"all" | WatchType>("all");
  const [verification, setVerification] = useState<"all" | "verified" | "flagged">("all");
  const [unreadOnly, setUnreadOnly] = useState(false);

  const typeOf = useMemo(() => new Map((watches.data ?? []).map((w) => [w.id, w.watch_type])), [watches.data]);
  const roomName = new Map(rooms.map((r) => [r.id, r.name]));
  const all = useMemo(() => [...(alerts.data ?? [])].sort((a, b) => (toDate(b.created_at)?.getTime() ?? 0) - (toDate(a.created_at)?.getTime() ?? 0)), [alerts.data]);
  const categoryOf = (a: (typeof all)[number]) => (a.payload?.watch_type as WatchType | undefined) ?? typeOf.get(a.watch_id);

  const list = all.filter(
    (a) =>
      (room === "all" || a.room_id === Number(room)) &&
      (category === "all" || categoryOf(a) === category) &&
      (verification === "all" || a.verification_status === verification) &&
      (!unreadOnly || !isRead(a.id)),
  );
  const unreadCount = all.filter((a) => !isRead(a.id)).length;

  return (
    <PageContainer>
      <PageHeader
        title="Alerts"
        description="Every change Nazar flagged, with the data and sources behind it."
        actions={
          unreadCount > 0 && (
            <Button variant="secondary" onClick={() => update({ readAlerts: [...new Set([...prefs.readAlerts, ...all.map((a) => a.id)])].slice(-500) })}>
              <CheckCheck /> Mark all read
            </Button>
          )
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Filter by category">
          {(
            [
              ["all", "All"],
              ["flight", "Flights"],
              ["stock", "Stocks"],
              ["job_notification", "Government jobs"],
              ["topic", "Other"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={category === value}
              onClick={() => setCategory(value)}
              className={cn(
                "h-8 cursor-pointer rounded-full border px-3.5 text-[13px] transition-colors",
                category === value ? "border-foreground bg-foreground text-white" : "border-border-strong bg-surface text-muted-foreground hover:text-foreground",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {rooms.length > 1 && (
            <NativeSelect value={room} onChange={(e) => setRoom(e.target.value)} aria-label="Filter by room" className="h-8 w-auto rounded-full pr-8 text-[13px]">
              <option value="all">All rooms</option>
              {rooms.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </NativeSelect>
          )}
          <NativeSelect value={verification} onChange={(e) => setVerification(e.target.value as typeof verification)} aria-label="Filter by verification" className="h-8 w-auto rounded-full pr-8 text-[13px]">
            <option value="all">Any source</option>
            <option value="verified">Verified only</option>
            <option value="flagged">Unconfirmed only</option>
          </NativeSelect>
          <button
            type="button"
            aria-pressed={unreadOnly}
            onClick={() => setUnreadOnly((v) => !v)}
            className={cn(
              "inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-full border px-3.5 text-[13px] transition-colors",
              unreadOnly ? "border-primary bg-mint text-primary" : "border-border-strong bg-surface text-muted-foreground hover:text-foreground",
            )}
          >
            Unread
            {unreadCount > 0 && <span className="tabular-nums">{unreadCount}</span>}
          </button>
        </div>
      </div>

      {alerts.loading && !alerts.data ? (
        <LoadingList />
      ) : alerts.error && !alerts.data ? (
        <ErrorState message={alerts.error} onRetry={alerts.reload} />
      ) : list.length === 0 ? (
        <EmptyState icon={Bell} title={all.length ? "No alerts match these filters" : "No alerts yet"} description={all.length ? "Try clearing a filter." : "When a watch hits its target, Nazar posts the alert here and in the room."} />
      ) : (
        <Card className="divide-y divide-border overflow-hidden">
          {list.map((a) => {
            const read = isRead(a.id);
            const type = categoryOf(a);
            return (
              <Link key={a.id} href={`/alerts/${a.id}`} className={cn("flex items-start gap-3 p-4 transition-colors hover:bg-muted/60", !read && "bg-primary/[0.03]")}>
                {type ? <WatchTypeIcon type={type} /> : <div className="size-9 shrink-0" />}
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-3">
                    <p className={cn("text-[14px] leading-snug", read ? "text-muted-foreground" : "font-semibold text-foreground")}>{a.title}</p>
                    <span className="shrink-0 text-xs text-subtle">{relativeTime(a.created_at)}</span>
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    {type && <Badge>{WATCH_TYPE_LABEL[type]}</Badge>}
                    <VerificationBadge status={a.verification_status} />
                    <span className="text-xs text-subtle">{roomName.get(a.room_id) ?? `Room #${a.room_id}`}</span>
                    {a.observed_value && <span className="ml-auto tabular-nums text-sm font-semibold text-primary">{a.observed_value}</span>}
                  </div>
                </div>
                {!read && <span className="mt-2 size-2 shrink-0 rounded-full bg-primary" aria-label="Unread" />}
              </Link>
            );
          })}
        </Card>
      )}
    </PageContainer>
  );
}
