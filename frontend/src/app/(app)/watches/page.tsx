"use client";

import { Plus } from "lucide-react";
import { useState } from "react";
import { PageContainer } from "@/components/app-shell";
import { ErrorState, LoadingList, PageHeader } from "@/components/common";
import { useRooms } from "@/components/rooms/rooms-context";
import { Button } from "@/components/ui/button";
import { WatchRow } from "@/components/watches/watch-card";
import { WatchDialog } from "@/components/watches/watch-dialog";
import { api } from "@/lib/api";
import type { Watch, WatchType } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

const FILTERS: { value: "all" | WatchType; label: string }[] = [
  { value: "all", label: "All" },
  { value: "flight", label: "Flights" },
  { value: "stock", label: "Stocks" },
  { value: "job_notification", label: "Government jobs" },
  { value: "topic", label: "Other" },
];

export default function WatchesPage() {
  const { rooms, openCreate } = useRooms();
  const { data, error, loading, reload, setData } = useApi(() => api.watches.list(), [], { pollMs: 60_000 });
  const [filter, setFilter] = useState<"all" | WatchType>("all");
  const [showDone, setShowDone] = useState(false);
  const [dialog, setDialog] = useState<{ watch?: Watch } | null>(null);
  const roomName = new Map(rooms.map((r) => [r.id, r.name]));

  const all = (data ?? []).filter((w) => w.status !== "deleted");
  const list = all.filter((w) => (filter === "all" || w.watch_type === filter) && (showDone || w.status !== "completed"));
  const count = (t: "all" | WatchType) => all.filter((w) => (t === "all" || w.watch_type === t) && w.status !== "completed").length;
  const onChange = (nw: Watch | null, id: number) => setData((prev) => (nw ? prev?.map((x) => (x.id === id ? nw : x)) : prev?.filter((x) => x.id !== id)));
  const doneCount = all.filter((w) => w.status === "completed").length;

  return (
    <PageContainer>
      <PageHeader
        title="Watches"
        description="Everything Nazar is keeping an eye on, across your rooms."
        actions={
          <Button onClick={() => (rooms.length ? setDialog({}) : openCreate())}>
            <Plus /> {rooms.length ? "New watch" : "Create a room first"}
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Filter by type">
          {FILTERS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={filter === value}
              onClick={() => setFilter(value)}
              className={cn(
                "inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-full border px-3.5 text-[13px] transition-colors",
                filter === value ? "border-foreground bg-foreground text-white" : "border-border-strong bg-surface text-muted-foreground hover:text-foreground",
              )}
            >
              {label}
              <span className={cn("tabular-nums", filter === value ? "text-white/60" : "text-subtle")}>{count(value)}</span>
            </button>
          ))}
        </div>
        {doneCount > 0 && (
          <label className="flex cursor-pointer items-center gap-2 text-[13px] text-muted-foreground">
            <input type="checkbox" checked={showDone} onChange={(e) => setShowDone(e.target.checked)} className="accent-[#0b7a5a]" /> Show {doneCount} completed
          </label>
        )}
      </div>

      {loading && !data ? (
        <LoadingList />
      ) : error && !data ? (
        <ErrorState message={error} onRetry={reload} />
      ) : list.length === 0 ? (
        <div className="rounded-[16px] border border-dashed border-border-strong px-6 py-14 text-center">
          <p className="text-[15px] font-medium">{filter === "all" ? "No watches yet" : `No ${FILTERS.find((f) => f.value === filter)?.label.toLowerCase()} watches`}</p>
          <p className="mx-auto mt-1 max-w-sm text-[13.5px] text-muted-foreground">Describe what to watch in plain words, or mention @Nazar in a room.</p>
          {rooms.length > 0 && (
            <Button size="sm" variant="secondary" className="mt-5" onClick={() => setDialog({})}>
              New watch
            </Button>
          )}
        </div>
      ) : (
        <ul className="divide-y divide-border overflow-hidden rounded-[16px] border border-border bg-surface">
          {list.map((w) => (
            <WatchRow key={w.id} watch={w} roomName={roomName.get(w.room_id)} onChange={onChange} onEdit={(watch) => setDialog({ watch })} />
          ))}
        </ul>
      )}

      <WatchDialog
        open={dialog !== null}
        onOpenChange={(o) => !o && setDialog(null)}
        rooms={rooms}
        watch={dialog?.watch}
        onSaved={(w) => setData((prev) => [w, ...(prev ?? []).filter((x) => x.id !== w.id)])}
      />
    </PageContainer>
  );
}
