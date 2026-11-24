"use client";

import { MoreHorizontal, Pause, Pencil, Play, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { StatusBadge, WatchTypeIcon } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { dateTime, latestValue, nextCheckLabel, relativeTime, targetCondition, watchTitle } from "@/lib/format";
import type { Watch } from "@/lib/types";

/** Pause / resume / delete with toasts. Edit is delegated to the caller's dialog. */
export function useWatchActions(onChange: (w: Watch | null, id: number) => void) {
  const [busy, setBusy] = useState(false);
  const run = async (w: Watch, action: "pause" | "resume" | "delete") => {
    setBusy(true);
    try {
      if (action === "delete") {
        await api.watches.remove(w.id);
        onChange(null, w.id);
        toast.success("Watch deleted");
      } else {
        const updated = await api.watches[action](w.id);
        onChange(updated ?? { ...w, status: action === "pause" ? "paused" : "active" }, w.id);
        toast.success(action === "pause" ? "Paused. Nazar won't check until resumed." : "Resumed. Nazar is watching again.");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };
  return { busy, run };
}

export function WatchCard({ watch, roomName, onChange, onEdit }: { watch: Watch; roomName?: string; onChange: (w: Watch | null, id: number) => void; onEdit: (w: Watch) => void }) {
  const { busy, run } = useWatchActions(onChange);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const value = latestValue(watch);
  const live = watch.status === "active" || watch.status === "paused";

  return (
    <Card className="group flex flex-col p-4 transition-colors hover:border-border-strong">
      <div className="flex items-start gap-3">
        <WatchTypeIcon type={watch.watch_type} />
        <div className="min-w-0 flex-1">
          <Link href={`/watches/${watch.id}`} className="block truncate font-semibold tracking-tight hover:text-primary">
            {watchTitle(watch.rule_json)}
          </Link>
          <p className="mt-0.5 line-clamp-2 text-[13px] text-muted-foreground">{targetCondition(watch.rule_json)}</p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label="Watch actions" disabled={busy}>
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {watch.status === "active" && (
              <DropdownMenuItem onSelect={() => run(watch, "pause")}>
                <Pause /> Pause
              </DropdownMenuItem>
            )}
            {(watch.status === "paused" || watch.status === "failed") && (
              <DropdownMenuItem onSelect={() => run(watch, "resume")}>
                <Play /> Resume
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onSelect={() => onEdit(watch)} disabled={watch.status === "completed"}>
              <Pencil /> Edit
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem destructive onSelect={() => setConfirmDelete(true)}>
              <Trash2 /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="mt-4 flex items-end justify-between gap-3">
        <div>
          <p className="text-[11px] text-subtle">Latest</p>
          <p className="tabular-nums text-lg font-semibold">{value ?? <span className="text-sm font-normal text-subtle">No check yet</span>}</p>
        </div>
        <StatusBadge status={watch.status} />
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-2 border-t border-border pt-3 text-xs">
        <div>
          <dt className="text-subtle">Last checked</dt>
          <dd className="mt-0.5 text-muted-foreground" title={dateTime(watch.last_checked_at)}>
            {relativeTime(watch.last_checked_at)}
          </dd>
        </div>
        <div>
          <dt className="text-subtle">Next check</dt>
          <dd className="mt-0.5 text-muted-foreground" title={dateTime(watch.next_check_at)}>
            {watch.status === "active" ? relativeTime(watch.next_check_at) : "—"}
          </dd>
        </div>
      </dl>
      {roomName && <p className="mt-2 truncate text-xs text-subtle">in {roomName}</p>}

      {live && (
        <div className="mt-3 flex gap-2 sm:hidden">
          <Button variant="secondary" size="sm" className="flex-1" disabled={busy} onClick={() => run(watch, watch.status === "active" ? "pause" : "resume")}>
            {watch.status === "active" ? <Pause /> : <Play />} {watch.status === "active" ? "Pause" : "Resume"}
          </Button>
          <Button variant="secondary" size="sm" className="flex-1" onClick={() => onEdit(watch)}>
            <Pencil /> Edit
          </Button>
        </div>
      )}

      <ConfirmDelete open={confirmDelete} onOpenChange={setConfirmDelete} busy={busy} onConfirm={() => run(watch, "delete").then(() => setConfirmDelete(false))} />
    </Card>
  );
}

export function ConfirmDelete({ open, onOpenChange, onConfirm, busy }: { open: boolean; onOpenChange: (o: boolean) => void; onConfirm: () => void; busy: boolean }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogTitle>Delete this watch?</DialogTitle>
        <DialogDescription>Nazar stops checking it. Past alerts stay in the room.</DialogDescription>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button variant="danger" onClick={onConfirm} loading={busy}>
            Delete
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** One watch as a list row: the default layout on the Watches page. */
export function WatchRow({ watch, roomName, onChange, onEdit }: { watch: Watch; roomName?: string; onChange: (w: Watch | null, id: number) => void; onEdit: (w: Watch) => void }) {
  const { busy, run } = useWatchActions(onChange);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const value = latestValue(watch);

  return (
    <li className="group flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-background sm:px-5">
      <WatchTypeIcon type={watch.watch_type} />
      <Link href={`/watches/${watch.id}`} className="min-w-0 flex-1">
        <p className="truncate text-[14px] font-medium group-hover:text-primary">{watchTitle(watch.rule_json)}</p>
        <p className="truncate text-[12.5px] text-muted-foreground">
          {targetCondition(watch.rule_json)}
          {roomName && <span className="text-subtle"> · {roomName}</span>}
        </p>
      </Link>
      <div className="hidden w-32 text-right md:block">
        {value && <p className="text-[14px] font-semibold tabular-nums">{value}</p>}
        <p className="text-[12px] text-subtle">{watch.last_checked_at ? `Checked ${relativeTime(watch.last_checked_at)}` : "Not checked yet"}</p>
      </div>
      <div className="hidden w-24 text-right lg:block">
        <StatusBadge status={watch.status} />
        <p className="text-[11.5px] text-subtle">{nextCheckLabel(watch)}</p>
      </div>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label="Watch actions" disabled={busy}>
            <MoreHorizontal />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {watch.status === "active" && (
            <DropdownMenuItem onSelect={() => run(watch, "pause")}>
              <Pause /> Pause
            </DropdownMenuItem>
          )}
          {(watch.status === "paused" || watch.status === "failed") && (
            <DropdownMenuItem onSelect={() => run(watch, "resume")}>
              <Play /> Resume
            </DropdownMenuItem>
          )}
          <DropdownMenuItem onSelect={() => onEdit(watch)} disabled={watch.status === "completed"}>
            <Pencil /> Edit
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem destructive onSelect={() => setConfirmDelete(true)}>
            <Trash2 /> Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ConfirmDelete open={confirmDelete} onOpenChange={setConfirmDelete} busy={busy} onConfirm={() => run(watch, "delete").then(() => setConfirmDelete(false))} />
    </li>
  );
}
