"use client";

import { ArrowLeft, PanelRight, Plus, Search, Settings2, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { ErrorState, LoadingList, StatusBadge, WatchTypeIcon } from "@/components/common";
import { VerificationBadge } from "@/components/alerts/alert-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/card";
import { Input } from "@/components/ui/field";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/misc";
import { Sparkline } from "@/components/watches/sparkline";
import { latestValue, relativeTime, targetCondition, watchTitle } from "@/lib/format";
import { usePrefs } from "@/lib/prefs";
import type { Alert, Member, Room, Watch, WatchType } from "@/lib/types";
import { cn } from "@/lib/utils";
import { AvatarStack } from "./chat-parts";

export function RoomHeader({
  room,
  members,
  mode,
  search,
  onSearch,
  onOpenPanel,
}: {
  room?: Room;
  members: Member[];
  mode: { mode: "nexconn" | "relay"; reason: string | null } | null;
  search: string;
  onSearch: (q: string) => void;
  watchCount?: number;
  onOpenPanel: () => void;
}) {
  const [searching, setSearching] = useState(false);
  const online = members.filter((m) => m.online).length;
  const hasPresence = members.some((m) => m.online !== undefined);
  const close = () => {
    onSearch("");
    setSearching(false);
  };

  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border bg-surface px-3 sm:px-5">
      <Button variant="ghost" size="icon-sm" asChild className="lg:hidden">
        <Link href="/chat" aria-label="Back to conversations">
          <ArrowLeft />
        </Link>
      </Button>
      {searching ? (
        <div className="flex flex-1 items-center gap-2">
          <Search className="size-4 shrink-0 text-subtle" />
          <Input
            autoFocus
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            placeholder="Search messages"
            className="h-9 border-0 bg-transparent px-1 focus-visible:ring-0"
            aria-label="Search messages"
            disabled={mode?.mode === "nexconn"}
            onKeyDown={(e) => e.key === "Escape" && close()}
          />
          <Button variant="ghost" size="icon-sm" onClick={close} aria-label="Close search">
            <X />
          </Button>
        </div>
      ) : (
        <>
          {room ? (
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-[15px] font-semibold">{room.name}</h1>
              <p className="truncate text-[12px] text-muted-foreground">
                {(members.length || room.member_count) === 1 ? "Just you" : `${members.length || room.member_count} members`}
                {hasPresence && online > 0 && ` · ${online} online`}
              </p>
            </div>
          ) : (
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-3 w-24" />
            </div>
          )}
          {members.length > 1 && (
            <span className="mr-2 hidden md:block">
              <AvatarStack members={members} max={3} size="size-6" />
            </span>
          )}
          {mode?.mode !== "nexconn" && (
            <Button variant="ghost" size="icon-sm" onClick={() => setSearching(true)} aria-label="Search messages" title="Search messages">
              <Search />
            </Button>
          )}
          {room && (
            <Button variant="ghost" size="icon-sm" asChild title="Members and invites">
              <Link href={`/rooms?room=${room.id}`} aria-label="Members and invites">
                <Settings2 />
              </Link>
            </Button>
          )}
          <Button variant="ghost" size="icon-sm" className="xl:hidden" onClick={onOpenPanel} aria-label="Watches and alerts" title="Watches and alerts">
            <PanelRight />
          </Button>
        </>
      )}
    </header>
  );
}

export function ActiveWatchCard({ watch }: { watch: Watch }) {
  const value = latestValue(watch);
  return (
    <Link href={`/watches/${watch.id}`} className="block rounded-[12px] px-3 py-3 transition-colors hover:bg-muted">
      <div className="flex items-start gap-3">
        <WatchTypeIcon type={watch.watch_type} className="size-8" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className="truncate text-[13.5px] font-medium">{watchTitle(watch.rule_json)}</p>
            <StatusBadge status={watch.status} />
          </div>
          <p className="truncate text-[12px] text-muted-foreground">{targetCondition(watch.rule_json)}</p>
          <div className="mt-2 flex items-end justify-between gap-2">
            <div>
              <p className="text-[15px] font-semibold tabular-nums">{value ?? <span className="text-[12px] font-normal text-subtle">Not checked yet</span>}</p>
              {watch.last_checked_at && <p className="text-[11.5px] text-subtle">Checked {relativeTime(watch.last_checked_at)}</p>}
            </div>
            <Sparkline points={watch.history} width={72} height={24} />
          </div>
        </div>
      </div>
    </Link>
  );
}

export function RecentAlertItem({ alert, type }: { alert: Alert; type?: WatchType }) {
  const { isRead } = usePrefs();
  const read = isRead(alert.id);
  return (
    <Link href={`/alerts/${alert.id}`} className="flex items-start gap-3 rounded-[10px] px-3 py-2.5 transition-colors hover:bg-muted">
      {type ? <WatchTypeIcon type={type} className="size-8" /> : <span className="size-8 shrink-0" />}
      <div className="min-w-0 flex-1">
        <p className={cn("truncate text-[13.5px]", read ? "text-muted-foreground" : "font-medium text-foreground")}>{alert.title}</p>
        <p className="mt-0.5 flex items-center gap-2 text-[12px] text-subtle">
          {alert.observed_value && <span className="tabular-nums text-foreground/70">{alert.observed_value}</span>}
          <span>{relativeTime(alert.created_at)}</span>
          <VerificationBadge status={alert.verification_status} />
        </p>
      </div>
      {!read && <span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary" aria-label="Unread" />}
    </Link>
  );
}

export function RoomSidePanel({
  watches,
  alerts,
  loading,
  error,
  onRetry,
  onNew,
}: {
  watches: Watch[];
  alerts: Alert[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onNew: () => void;
}) {
  const typeOf = new Map(watches.map((w) => [w.id, w.watch_type]));
  const active = watches.filter((w) => w.status !== "completed");
  return (
    <Tabs defaultValue="watches" className="flex h-full flex-col">
      <div className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-border px-3 pr-12 xl:pr-3">
        <TabsList className="h-8 border-0 bg-transparent p-0">
          <TabsTrigger value="watches" className="data-[state=active]:bg-muted data-[state=active]:shadow-none">
            Watches
          </TabsTrigger>
          <TabsTrigger value="alerts" className="data-[state=active]:bg-muted data-[state=active]:shadow-none">
            Alerts
          </TabsTrigger>
        </TabsList>
        <Button variant="ghost" size="icon-sm" onClick={onNew} aria-label="New watch" title="New watch">
          <Plus />
        </Button>
      </div>
      <TabsContent value="watches" className="scrollbar-thin min-h-0 flex-1 overflow-y-auto p-2 data-[state=inactive]:hidden">
        {loading ? (
          <LoadingList rows={2} />
        ) : error ? (
          <ErrorState message={error} onRetry={onRetry} />
        ) : active.length === 0 ? (
          <div className="px-4 py-12 text-center">
            <p className="text-[13.5px] font-medium">No watches yet</p>
            <p className="mt-1 text-[13px] text-muted-foreground">Mention @Nazar in the chat, or add one here.</p>
            <Button size="sm" variant="secondary" className="mt-4" onClick={onNew}>
              New watch
            </Button>
          </div>
        ) : (
          active.map((w) => <ActiveWatchCard key={w.id} watch={w} />)
        )}
      </TabsContent>
      <TabsContent value="alerts" className="scrollbar-thin min-h-0 flex-1 overflow-y-auto p-2 data-[state=inactive]:hidden">
        {alerts.length === 0 ? <p className="px-4 py-12 text-center text-[13px] text-muted-foreground">No alerts in this room yet.</p> : alerts.map((a) => <RecentAlertItem key={a.id} alert={a} type={(a.payload?.watch_type as WatchType) ?? typeOf.get(a.watch_id)} />)}
      </TabsContent>
    </Tabs>
  );
}
