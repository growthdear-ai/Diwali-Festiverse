"use client";

import { Bell, ChevronsUpDown, Eye, LayoutGrid, LogOut, Menu, MessageCircle, Plus, Settings, Users } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Logo, TONES, toneFor } from "@/components/common";
import { initials, UserAvatar } from "@/components/chat/chat-parts";
import { useRooms } from "@/components/rooms/rooms-context";
import { NotificationBell, SearchButton, useAlertsFeed } from "@/components/shell/search-and-notifications";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { usePrefs, type TKey } from "@/lib/prefs";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

const NAV: { href: string; key: TKey; icon: React.ComponentType<{ className?: string }>; count?: "watches" | "alerts" }[] = [
  { href: "/dashboard", key: "dashboard", icon: LayoutGrid },
  { href: "/chat", key: "conversations", icon: MessageCircle },
  { href: "/watches", key: "watches", icon: Eye, count: "watches" },
  { href: "/alerts", key: "alerts", icon: Bell, count: "alerts" },
  { href: "/rooms", key: "rooms", icon: Users },
];

const itemBase = "flex items-center gap-2.5 rounded-[9px] text-[13.5px] transition-all";
const itemActive = "bg-surface font-medium text-foreground shadow-[0_1px_2px_rgb(24_24_27/0.06),0_0_0_1px_rgb(24_24_27/0.05)]";
const itemIdle = "text-muted-foreground hover:bg-black/[0.035] hover:text-foreground";

function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { t, isRead } = usePrefs();
  const { rooms, loading, openCreate } = useRooms();
  const alertsFeed = useAlertsFeed();
  const watchesFeed = useApi(() => api.watches.list(), [], { pollMs: 60_000 });
  const counts = {
    watches: (watchesFeed.data ?? []).filter((w) => w.status === "active").length,
    alerts: (alertsFeed.data ?? []).filter((a) => !isRead(a.id)).length,
  };
  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  const create = () => {
    onNavigate?.();
    openCreate();
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center justify-between px-4">
        <Logo href="/dashboard" />
        <NotificationBell align="start" />
      </div>

      <div className="px-3 pb-3">
        <SearchButton />
      </div>

      <nav className="space-y-0.5 px-2" aria-label="Main">
        {NAV.map(({ href, key, icon: Icon, count }) => {
          const active = isActive(href);
          const n = count ? counts[count] : 0;
          return (
            <Link key={href} href={href} onClick={onNavigate} aria-current={active ? "page" : undefined} className={cn("group px-2.5 py-[7px]", itemBase, active ? itemActive : itemIdle)}>
              <Icon className={cn("size-4 transition-colors", active ? "text-primary" : "text-subtle group-hover:text-muted-foreground")} />
              <span className="flex-1">{t(key)}</span>
              {n > 0 && (
                <span
                  className={cn(
                    "min-w-5 rounded-full px-1.5 text-center text-[11px] font-medium leading-5 tabular-nums",
                    count === "alerts" ? "bg-primary text-white" : "bg-black/[0.05] text-muted-foreground",
                  )}
                  aria-label={count === "alerts" ? `${n} unread` : `${n} active`}
                >
                  {n}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="mt-6 flex min-h-0 flex-1 flex-col">
        <div className="flex items-center justify-between px-4 pb-1.5">
          <p className="text-[11.5px] font-medium text-subtle">Your rooms</p>
          <Button variant="ghost" size="icon-sm" className="size-6 rounded-[7px]" aria-label={t("createRoom")} title={t("createRoom")} onClick={create}>
            <Plus />
          </Button>
        </div>
        <div className="scrollbar-thin min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
          {loading && !rooms.length ? (
            [0, 1, 2].map((i) => <Skeleton key={i} className="mx-2 my-2 h-7" />)
          ) : rooms.length === 0 ? (
            <button
              type="button"
              onClick={create}
              className="flex w-full cursor-pointer items-center gap-2.5 rounded-[9px] border border-dashed border-border-strong px-2.5 py-2 text-left text-[13px] text-muted-foreground hover:border-primary/40 hover:text-primary"
            >
              <Plus className="size-4" /> Create your first room
            </button>
          ) : (
            rooms.map((r) => {
              const active = pathname === `/chat/${r.id}`;
              const online = r.members?.some((m) => m.online && m.user_id !== user?.id);
              return (
                <Link key={r.id} href={`/chat/${r.id}`} onClick={onNavigate} className={cn("px-2 py-1.5", itemBase, active ? itemActive : itemIdle)}>
                  <span className={cn("relative grid size-6 shrink-0 place-items-center rounded-[7px] text-[10px] font-semibold", TONES[toneFor(r.id)].soft)}>
                    {initials(r.name)}
                    {online && <span className="absolute -bottom-0.5 -right-0.5 size-2 rounded-full bg-[#22c55e] ring-2 ring-[#f7f7f5]" aria-label="Someone is online" />}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{r.name}</span>
                  <span className="text-[11px] tabular-nums text-subtle" title={`${r.member_count} members`}>
                    {r.member_count}
                  </span>
                </Link>
              );
            })
          )}
        </div>
      </div>

      {user && (
        <div className="border-t border-border p-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button type="button" className="flex w-full cursor-pointer items-center gap-2.5 rounded-[9px] px-2 py-2 text-left transition-colors hover:bg-black/[0.035]">
                <UserAvatar id={user.id} name={user.name} className="size-8 ring-0" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium">{user.name}</span>
                  <span className="block truncate text-[11.5px] text-subtle">{user.email}</span>
                </span>
                <ChevronsUpDown className="size-4 text-subtle" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" side="top" className="w-[220px]">
              <DropdownMenuItem asChild>
                <Link href="/settings" onClick={onNavigate}>
                  <Settings /> {t("settings")}
                </Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem destructive onSelect={logout}>
                <LogOut /> {t("logout")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}
    </div>
  );
}

const MOBILE_TABS = [
  { href: "/dashboard", icon: LayoutGrid, key: "dashboard" as TKey },
  { href: "/chat", icon: MessageCircle, key: "conversations" as TKey },
  { href: "/watches", icon: Eye, key: "watches" as TKey },
  { href: "/alerts", icon: Bell, key: "alerts" as TKey },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { t } = usePrefs();
  const [menuOpen, setMenuOpen] = useState(false);
  const inChat = pathname.startsWith("/chat/");

  return (
    <div className="flex h-dvh flex-col">
      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-60 shrink-0 border-r border-border bg-[#f7f7f5] lg:block">
          <SidebarBody />
        </aside>

        <div className="flex min-w-0 flex-1 flex-col bg-surface">
          {!inChat && (
            <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-surface px-3 lg:hidden">
              <Logo href="/dashboard" />
              <div className="flex items-center">
                <SearchButton compact />
                <NotificationBell />
                <Button variant="ghost" size="icon" onClick={() => setMenuOpen(true)} aria-label="Open menu">
                  <Menu />
                </Button>
              </div>
            </header>
          )}
          <main className={cn("min-h-0 flex-1", inChat ? "overflow-hidden" : "scrollbar-thin overflow-y-auto pb-20 lg:pb-0")}>{children}</main>
          {!inChat && (
            <nav className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-border bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden" aria-label="Mobile">
              {MOBILE_TABS.map(({ href, icon: Icon, key }) => {
                const active = pathname.startsWith(href);
                return (
                  <Link key={href} href={href} className={cn("flex flex-col items-center gap-1 py-2.5 text-[11px] font-medium", active ? "text-primary" : "text-subtle")}>
                    <Icon className="size-5" />
                    {t(key)}
                  </Link>
                );
              })}
            </nav>
          )}
        </div>
      </div>

      <Dialog open={menuOpen} onOpenChange={setMenuOpen}>
        <DialogContent side="left" className="w-[min(280px,85vw)] bg-[#f7f7f5] p-0">
          <DialogTitle className="sr-only">Menu</DialogTitle>
          <SidebarBody onNavigate={() => setMenuOpen(false)} />
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function PageContainer({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("mx-auto w-full max-w-5xl px-4 py-8 sm:px-8 lg:py-12", className)}>{children}</div>;
}
