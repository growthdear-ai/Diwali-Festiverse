"use client";

import { Bell, CheckCheck, CornerDownLeft, Search, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { WatchTypeIcon } from "@/components/common";
import { RecentAlertItem } from "@/components/chat/room-panels";
import { useRooms } from "@/components/rooms/rooms-context";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { relativeTime, toDate, watchTitle, WATCH_TYPE_LABEL } from "@/lib/format";
import { usePrefs } from "@/lib/prefs";
import type { WatchType } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

/** Shared alerts feed for the bell + search (one poll for both). */
export function useAlertsFeed() {
  return useApi(() => api.alerts.list(), [], { pollMs: 60_000 });
}

export function NotificationBell({ align = "end", className }: { align?: "start" | "end"; className?: string }) {
  const { isRead, update, prefs } = usePrefs();
  const router = useRouter();
  const { data } = useAlertsFeed();
  const alerts = useMemo(() => [...(data ?? [])].sort((a, b) => (toDate(b.created_at)?.getTime() ?? 0) - (toDate(a.created_at)?.getTime() ?? 0)), [data]);
  const unread = alerts.filter((a) => !isRead(a.id)).length;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" className={cn("relative", className)} aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}>
          <Bell />
          {unread > 0 && <span className="absolute right-1 top-1 grid min-w-3.5 place-items-center rounded-full bg-primary px-0.5 text-[9px] font-semibold leading-[14px] text-white">{unread > 9 ? "9+" : unread}</span>}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align={align} className="w-[min(360px,92vw)] p-0">
        <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
          <p className="text-sm font-semibold">Notifications</p>
          {unread > 0 && (
            <button type="button" className="inline-flex cursor-pointer items-center gap-1 text-xs font-medium text-primary hover:underline" onClick={() => update({ readAlerts: [...new Set([...prefs.readAlerts, ...alerts.map((a) => a.id)])].slice(-500) })}>
              <CheckCheck className="size-3.5" /> Mark all read
            </button>
          )}
        </div>
        <div className="scrollbar-thin max-h-96 overflow-y-auto p-1.5">
          {alerts.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-muted-foreground">You&apos;re all caught up.</p>
          ) : (
            alerts.slice(0, 8).map((a) => <RecentAlertItem key={a.id} alert={a} type={a.payload?.watch_type as WatchType | undefined} />)
          )}
        </div>
        <button type="button" onClick={() => router.push("/alerts")} className="block w-full cursor-pointer border-t border-border px-3 py-2.5 text-center text-[13px] font-medium text-muted-foreground hover:bg-muted hover:text-foreground">
          View all alerts
        </button>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

type Hit = { key: string; label: string; sub: string; href: string; icon: React.ReactNode };

export function SearchButton({ className, compact }: { className?: string; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (compact) return; // only the sidebar instance owns the Ctrl+K shortcut, so one dialog opens
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [compact]);
  return (
    <>
      {compact ? (
        <Button variant="ghost" size="icon-sm" onClick={() => setOpen(true)} aria-label="Search" className={className}>
          <Search />
        </Button>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className={cn("flex h-8 w-full cursor-pointer items-center gap-2 rounded-[8px] border border-border bg-surface px-2.5 text-[13px] text-subtle transition-colors hover:border-border-strong hover:text-muted-foreground", className)}
        >
          <Search className="size-3.5" /> Search
          <kbd className="ml-auto font-sans text-[11px] text-subtle">Ctrl K</kbd>
        </button>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="top-[12vh] max-w-xl translate-y-0 p-0">
          <DialogTitle className="sr-only">Search</DialogTitle>
          {open && <SearchPanel onDone={() => setOpen(false)} />}
        </DialogContent>
      </Dialog>
    </>
  );
}

function SearchPanel({ onDone }: { onDone: () => void }) {
  const router = useRouter();
  const { rooms } = useRooms();
  const alerts = useAlertsFeed();
  const watches = useApi(() => api.watches.list(), []);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const roomName = new Map(rooms.map((r) => [r.id, r.name]));
  const term = q.trim().toLowerCase();
  const match = (...s: (string | null | undefined)[]) => !term || s.some((x) => x?.toLowerCase().includes(term));

  const groups: { title: string; hits: Hit[] }[] = [
    {
      title: "Rooms",
      hits: rooms
        .filter((r) => match(r.name, r.description))
        .slice(0, 5)
        .map((r) => ({ key: `r${r.id}`, label: r.name, sub: `${r.member_count} members`, href: `/chat/${r.id}`, icon: <span className="grid size-7 place-items-center rounded-[8px] bg-mint text-primary"><Users className="size-3.5" /></span> })),
    },
    {
      title: "Watches",
      hits: (watches.data ?? [])
        .filter((w) => w.status !== "deleted" && match(watchTitle(w.rule_json), WATCH_TYPE_LABEL[w.watch_type]))
        .slice(0, 5)
        .map((w) => ({ key: `w${w.id}`, label: watchTitle(w.rule_json), sub: `${WATCH_TYPE_LABEL[w.watch_type]} · ${roomName.get(w.room_id) ?? "Room"}`, href: `/watches/${w.id}`, icon: <WatchTypeIcon type={w.watch_type} className="size-7 [&_svg]:size-3.5" /> })),
    },
    {
      title: "Alerts",
      hits: (alerts.data ?? [])
        .filter((a) => match(a.title, a.observed_value, a.explanation))
        .slice(0, 6)
        .map((a) => ({ key: `a${a.id}`, label: a.title, sub: `${roomName.get(a.room_id) ?? "Room"} · ${relativeTime(a.created_at)}`, href: `/alerts/${a.id}`, icon: <span className="grid size-7 place-items-center rounded-[8px] bg-muted"><Bell className="size-3.5 text-muted-foreground" /></span> })),
    },
  ].filter((g) => g.hits.length);
  const flat = groups.flatMap((g) => g.hits);
  const sel = flat.length ? Math.min(active, flat.length - 1) : -1;

  function go(h: Hit) {
    onDone();
    router.push(h.href);
  }

  return (
    <div>
      <div className="flex items-center gap-2.5 border-b border-border px-4">
        <Search className="size-4 text-subtle" />
        <input
          autoFocus
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              e.preventDefault();
              setActive((i) => (e.key === "ArrowDown" ? Math.min(i + 1, flat.length - 1) : Math.max(i - 1, 0)));
            }
            if (e.key === "Enter" && sel >= 0) go(flat[sel]);
          }}
          placeholder="Search rooms, watches and alerts…"
          aria-label="Search"
          className="h-12 flex-1 bg-transparent text-[15px] placeholder:text-subtle focus:outline-none"
        />
      </div>
      <div className="scrollbar-thin max-h-[60vh] overflow-y-auto p-2">
        {flat.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">{alerts.loading || watches.loading ? "Loading…" : `Nothing matches “${q}”.`}</p>
        ) : (
          groups.map((g) => (
            <div key={g.title} className="mb-1">
              <p className="px-2.5 pb-1 pt-2 text-[10.5px] font-semibold text-subtle">{g.title}</p>
              {g.hits.map((h) => {
                const i = flat.indexOf(h);
                return (
                  <button key={h.key} type="button" onMouseEnter={() => setActive(i)} onClick={() => go(h)} className={cn("flex w-full cursor-pointer items-center gap-3 rounded-[10px] px-2.5 py-2 text-left", i === sel ? "bg-muted" : "")}>
                    {h.icon}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13.5px] font-medium">{h.label}</span>
                      <span className="block truncate text-[11.5px] text-subtle">{h.sub}</span>
                    </span>
                    {i === sel && <CornerDownLeft className="size-3.5 text-subtle" />}
                  </button>
                );
              })}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
