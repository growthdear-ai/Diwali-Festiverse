"use client";

import { ArrowRight, Bell, Clock, Eye, Plus, Users, Vote } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { ErrorState, LoadingList, StatusBadge, TONES, toneFor, WatchTypeIcon, type Tone } from "@/components/common";
import { RecentAlertItem } from "@/components/chat/room-panels";
import { useRooms } from "@/components/rooms/rooms-context";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/card";
import { InteractiveGrid } from "@/components/ui/interactive-grid";
import { Sparkline } from "@/components/watches/sparkline";
import { WatchDialog } from "@/components/watches/watch-dialog";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { latestValue, nextCheckLabel, plural, relativeTime, targetCondition, toDate, WATCH_TYPE_LABEL, watchTitle } from "@/lib/format";
import type { Alert, Watch, WatchType } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
const time = (iso?: string | null) => toDate(iso)?.getTime() ?? 0;

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

type IconT = React.ComponentType<{ className?: string }>;

function Panel({ title, icon: Icon, tone, action, children, className }: { title: string; icon: IconT; tone: Tone; action?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("rounded-[16px] border border-border bg-surface", className)}>
      <header className="flex items-center justify-between px-5 pb-2 pt-4">
        <h2 className="flex items-center gap-2 text-[14px] font-semibold">
          <span className={cn("grid size-6 place-items-center rounded-[7px]", TONES[tone].soft)}>
            <Icon className="size-3.5" />
          </span>
          {title}
        </h2>
        {action}
      </header>
      {children}
    </section>
  );
}

function ViewAll({ href }: { href: string }) {
  return (
    <Link href={href} className="inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground">
      View all <ArrowRight className="size-3.5" />
    </Link>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="px-5 pb-6 pt-2 text-[13.5px] text-muted-foreground">{children}</p>;
}

export default function DashboardPage() {
  const { user } = useAuth();
  const { rooms, openCreate } = useRooms();
  const watches = useApi(() => api.watches.list(), [], { pollMs: 60_000 });
  const alerts = useApi(() => api.alerts.list(), [], { pollMs: 60_000 });
  const [dialog, setDialog] = useState<{ watch?: Watch } | null>(null);

  const live = useMemo(() => (watches.data ?? []).filter((w) => w.status !== "deleted" && w.status !== "completed"), [watches.data]);
  const typeOf = new Map((watches.data ?? []).map((w) => [w.id, w.watch_type]));
  const roomName = new Map(rooms.map((r) => [r.id, r.name]));
  const alertList = useMemo(() => [...(alerts.data ?? [])].sort((a, b) => time(b.created_at) - time(a.created_at)), [alerts.data]);

  // Real derived numbers only.
  const [now] = useState(() => Date.now()); // "this week" window, fixed per visit
  const active = live.filter((w) => w.status === "active");
  const paused = live.length - active.length;
  const thisWeek = alertList.filter((a) => now - time(a.created_at) < WEEK_MS);
  const awaitingVote = alertList.filter((a) => a.votes && !a.votes.my_vote);
  const nextChecks = active.filter((w) => w.next_check_at).sort((a, b) => time(a.next_check_at) - time(b.next_check_at));
  const hasTrend = live.some((w) => (w.history?.filter((h) => typeof h.observed_value === "number").length ?? 0) > 1);
  const watchesPerRoom = (id: number) => live.filter((w) => w.room_id === id).length;
  const loading = (watches.loading && !watches.data) || (alerts.loading && !alerts.data);

  const metrics: { label: string; value: number; sub: string; href: string; tone: Tone; icon: IconT }[] = [
    { label: "Watching", value: active.length, sub: paused ? `${paused} paused` : "All running", href: "/watches", tone: "emerald", icon: Eye },
    { label: "Alerts this week", value: thisWeek.length, sub: `${alertList.length} in total`, href: "/alerts", tone: "sky", icon: Bell },
    { label: "Waiting for your vote", value: awaitingVote.length, sub: awaitingVote.length ? "Your family is deciding" : "You're up to date", href: "/alerts", tone: "amber", icon: Vote },
    { label: "Rooms", value: rooms.length, sub: `${plural(rooms.reduce((n, r) => n + r.member_count, 0), "member")} in total`, href: "/rooms", tone: "violet", icon: Users },
  ];

  const newWatch = () => (rooms.length ? setDialog({}) : openCreate());

  return (
    <div className="pb-12">
      {/* Header band with the interactive grid in the background */}
      <div className="relative overflow-hidden border-b border-border">
        <InteractiveGrid cellSize={44} className="text-primary opacity-60 [mask-image:radial-gradient(ellipse_70%_90%_at_80%_0%,white,transparent_75%)]" />
        <div className="relative mx-auto max-w-6xl px-4 pb-8 pt-10 sm:px-8 lg:pt-12">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-[13px] text-muted-foreground">{new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}</p>
              <h1 className="mt-1 text-[30px] font-semibold tracking-[-0.03em]">
                {greeting()}, {user?.name.split(" ")[0]}
              </h1>
            </div>
            <Button onClick={newWatch}>
              <Plus /> {rooms.length ? "New watch" : "Create room"}
            </Button>
          </div>

          <dl className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
            {metrics.map((m) => (
              <Link
                key={m.label}
                href={m.href}
                className={cn(
                  "group relative overflow-hidden rounded-[14px] border border-border bg-gradient-to-b to-white px-4 py-4 transition-all hover:-translate-y-0.5 hover:shadow-[var(--shadow-md)]",
                  TONES[m.tone].wash,
                )}
              >
                <div className="flex items-center justify-between">
                  <dt className="text-[12.5px] text-muted-foreground">{m.label}</dt>
                  <span className={cn("grid size-7 place-items-center rounded-[8px] bg-white/80 shadow-[0_0_0_1px_rgb(24_24_27/0.04)]", TONES[m.tone].text)}>
                    <m.icon className="size-3.5" />
                  </span>
                </div>
                <dd className="mt-2">
                  {loading ? <Skeleton className="h-7 w-10" /> : <span className="text-[28px] font-semibold leading-none tracking-[-0.03em] tabular-nums">{m.value}</span>}
                </dd>
                <p className={cn("mt-1.5 truncate text-[12px]", m.value > 0 && m.tone === "amber" ? TONES.amber.text : "text-subtle")}>{m.sub}</p>
              </Link>
            ))}
          </dl>
        </div>
      </div>

      <div className="mx-auto grid max-w-6xl gap-5 px-4 pt-8 sm:px-8 lg:grid-cols-[1fr_320px]">
        <div className="min-w-0 space-y-5">
          {awaitingVote.length > 0 && (
            <Panel title="Needs your vote" icon={Vote} tone="amber" className="border-[#fde68a]/70" action={<span className="text-[12.5px] text-subtle">{awaitingVote.length} open</span>}>
              <ul className="px-2 pb-2">
                {awaitingVote.slice(0, 3).map((a: Alert) => (
                  <li key={a.id}>
                    <Link href={`/alerts/${a.id}`} className="flex items-center gap-3 rounded-[10px] px-3 py-2.5 transition-colors hover:bg-muted">
                      {(a.payload?.watch_type as WatchType) || typeOf.get(a.watch_id) ? <WatchTypeIcon type={((a.payload?.watch_type as WatchType) ?? typeOf.get(a.watch_id))!} className="size-8" /> : null}
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13.5px] font-medium">{a.title}</p>
                        <p className="truncate text-[12px] text-muted-foreground">
                          {roomName.get(a.room_id) ?? "Room"} · {a.votes!.total_votes} of {a.votes!.total_members || "?"} voted · {relativeTime(a.created_at)}
                        </p>
                      </div>
                      {a.observed_value && <span className="hidden text-[14px] font-semibold tabular-nums sm:block">{a.observed_value}</span>}
                      <span className="rounded-full bg-[#f59e0b] px-3 py-1 text-[12px] font-medium text-white">Vote</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          <Panel title="Watches" icon={Eye} tone="emerald" action={<ViewAll href="/watches" />}>
            {watches.loading && !watches.data ? (
              <div className="p-5">
                <LoadingList rows={2} />
              </div>
            ) : watches.error && !watches.data ? (
              <div className="p-5">
                <ErrorState message={watches.error} onRetry={watches.reload} />
              </div>
            ) : live.length === 0 ? (
              <Empty>{rooms.length ? "Nothing watched yet. Mention @Nazar in a room, or add a watch here." : "Create a room, then ask @Nazar to watch something."}</Empty>
            ) : (
              <div>
                <table className="w-full table-fixed text-left sm:table-auto">
                  <thead>
                    <tr className="text-[12px] text-subtle">
                      <th className="px-5 pb-2 font-normal">Watch</th>
                      {hasTrend && <th className="hidden px-3 pb-2 font-normal md:table-cell">Trend</th>}
                      <th className="hidden px-3 pb-2 text-right font-normal sm:table-cell">Current</th>
                      <th className="hidden px-5 pb-2 text-right font-normal sm:table-cell">Next check</th>
                    </tr>
                  </thead>
                  <tbody className="border-t border-border">
                    {live.slice(0, 6).map((w) => {
                      const value = latestValue(w);
                      return (
                        <tr key={w.id} className="group border-b border-border last:border-0">
                          <td className="px-5 py-3">
                            <Link href={`/watches/${w.id}`} className="flex items-center gap-3">
                              <WatchTypeIcon type={w.watch_type} className="size-8" />
                              <span className="min-w-0">
                                <span className="block truncate text-[13.5px] font-medium group-hover:text-primary">{watchTitle(w.rule_json)}</span>
                                <span className="block truncate text-[12px] text-muted-foreground">
                                  {WATCH_TYPE_LABEL[w.watch_type]} · {targetCondition(w.rule_json)}
                                </span>
                              </span>
                            </Link>
                          </td>
                          {hasTrend && (
                            <td className="hidden px-3 py-3 md:table-cell">
                              <Sparkline points={w.history} width={72} height={24} />
                            </td>
                          )}
                          <td className="hidden px-3 py-3 text-right sm:table-cell">
                            {value ? <p className="text-[14px] font-semibold tabular-nums">{value}</p> : <p className="text-[12.5px] text-subtle">Not checked yet</p>}
                            <StatusBadge status={w.status} />
                          </td>
                          <td className="hidden whitespace-nowrap px-5 py-3 text-right text-[12.5px] text-muted-foreground sm:table-cell">{nextCheckLabel(w)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <Panel title="Latest alerts" icon={Bell} tone="sky" action={<ViewAll href="/alerts" />}>
            {alerts.loading && !alerts.data ? (
              <div className="p-5">
                <LoadingList rows={2} />
              </div>
            ) : alerts.error && !alerts.data ? (
              <div className="p-5">
                <ErrorState message={alerts.error} onRetry={alerts.reload} />
              </div>
            ) : alertList.length === 0 ? (
              <Empty>When a watch hits its target, Nazar posts the alert here and in the room.</Empty>
            ) : (
              <div className="px-2 pb-2">
                {alertList.slice(0, 5).map((a) => (
                  <RecentAlertItem key={a.id} alert={a} type={(a.payload?.watch_type as WatchType) ?? typeOf.get(a.watch_id)} />
                ))}
              </div>
            )}
          </Panel>
        </div>

        <aside className="space-y-5">
          <Panel title="Upcoming checks" icon={Clock} tone="emerald">
            {nextChecks.length === 0 ? (
              <Empty>No checks scheduled.</Empty>
            ) : (
              <ol className="px-5 pb-4">
                {nextChecks.slice(0, 5).map((w) => (
                  <li key={w.id} className="flex items-center justify-between gap-3 border-b border-border py-2.5 last:border-0">
                    <Link href={`/watches/${w.id}`} className="min-w-0 truncate text-[13px] hover:text-primary">
                      {watchTitle(w.rule_json)}
                    </Link>
                    <span className="shrink-0 text-[12.5px] tabular-nums text-muted-foreground">{nextCheckLabel(w)}</span>
                  </li>
                ))}
              </ol>
            )}
          </Panel>

          <Panel title="Rooms" icon={Users} tone="violet" action={<ViewAll href="/rooms" />}>
            {rooms.length === 0 ? (
              <div className="px-5 pb-5">
                <p className="text-[13.5px] text-muted-foreground">Rooms are where your family talks to Nazar.</p>
                <Button size="sm" variant="secondary" className="mt-3" onClick={openCreate}>
                  Create a room
                </Button>
              </div>
            ) : (
              <ul className="px-2 pb-2">
                {rooms.slice(0, 5).map((r) => (
                  <li key={r.id}>
                    <Link href={`/chat/${r.id}`} className="flex items-center gap-3 rounded-[10px] px-3 py-2.5 transition-colors hover:bg-muted">
                      <span className={cn("grid size-8 shrink-0 place-items-center rounded-[9px] text-[11px] font-semibold", TONES[toneFor(r.id)].soft)}>
                        {r.name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase()}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13.5px] font-medium">{r.name}</span>
                        <span className="block text-[12px] text-muted-foreground">
                          {r.member_count === 1 ? "Just you" : plural(r.member_count, "member")} · {watchesPerRoom(r.id)} watching
                        </span>
                      </span>
                      <ArrowRight className="size-4 shrink-0 text-subtle" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </aside>
      </div>

      <WatchDialog
        open={dialog !== null}
        onOpenChange={(o) => !o && setDialog(null)}
        rooms={rooms}
        watch={dialog?.watch}
        onSaved={(w) => watches.setData((prev) => [w, ...(prev ?? []).filter((x) => x.id !== w.id)])}
      />
    </div>
  );
}
