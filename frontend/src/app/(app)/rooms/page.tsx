"use client";

import { Check, Copy, Crown, Link2, LogIn, MessageCircle, MessagesSquare, Plus, Users } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { toast } from "sonner";
import { PageContainer } from "@/components/app-shell";
import { EmptyState, ErrorState, LoadingList, PageHeader, TONES, toneFor } from "@/components/common";
import { UserAvatar } from "@/components/chat/chat-parts";
import { useRooms } from "@/components/rooms/rooms-context";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardContent, CardHeader, CardTitle, Skeleton } from "@/components/ui/card";
import { Input } from "@/components/ui/field";
import { api } from "@/lib/api";
import { appUrl } from "@/lib/env";
import { dateTime, plural, relativeTime } from "@/lib/format";
import type { Invite } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";
import { roomInviteText, whatsappUrl } from "@/lib/whatsapp";

export default function RoomsPage() {
  return (
    <Suspense>
      <Rooms />
    </Suspense>
  );
}

function Rooms() {
  const { rooms, loading, error, reload, openCreate, openJoin } = useRooms();
  const params = useSearchParams();
  const router = useRouter();
  const selectedId = Number(params.get("room")) || rooms[0]?.id;

  return (
    <PageContainer>
      <PageHeader
        title="Rooms"
        description="Family and friends groups where @Nazar posts alerts."
        actions={
          <>
            <Button variant="secondary" onClick={openJoin}>
              <LogIn /> Join with code
            </Button>
            <Button onClick={openCreate}>
              <Plus /> Create room
            </Button>
          </>
        }
      />
      {loading && !rooms.length ? (
        <LoadingList />
      ) : error && !rooms.length ? (
        <ErrorState message={error} onRetry={reload} />
      ) : rooms.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No rooms yet"
          description="Create a room and invite your family on WhatsApp. Everyone sees Nazar's alerts and votes together."
          action={
            <Button onClick={openCreate}>
              <Plus /> Create your first room
            </Button>
          }
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
          <div className="space-y-2">
            {rooms.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => router.replace(`/rooms?room=${r.id}`, { scroll: false })}
                className={cn(
                  "flex w-full cursor-pointer items-center gap-3 rounded-[var(--radius)] border p-3 text-left transition-colors",
                  r.id === selectedId ? "border-primary/40 bg-primary/5" : "border-border bg-card hover:border-border-strong",
                )}
              >
                <span className={cn("grid size-10 shrink-0 place-items-center rounded-[10px] text-[13px] font-semibold", TONES[toneFor(r.id)].soft)}>{r.name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase()}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{r.name}</span>
                  <span className="block text-xs text-muted-foreground">
                    {plural(r.member_count, "member")}{r.my_role === "owner" ? " · You own this room" : ""}
                  </span>
                </span>
              </button>
            ))}
          </div>
          {selectedId && <RoomDetail key={selectedId} roomId={selectedId} />}
        </div>
      )}
    </PageContainer>
  );
}

function RoomDetail({ roomId }: { roomId: number }) {
  const room = useApi(() => api.rooms.get(roomId), [roomId]);
  const [invite, setInvite] = useState<Invite | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let live = true;
    api.rooms
      .invite(roomId)
      .then((i) => live && setInvite(i))
      .catch((e) => live && setInviteError(e instanceof Error ? e.message : "Could not create invite link"));
    return () => {
      live = false;
    };
  }, [roomId]);

  if (room.error && !room.data) return <ErrorState message={room.error} onRetry={room.reload} />;
  if (!room.data) return <LoadingList rows={2} />;

  const r = room.data;
  const inviteUrl = invite?.invite_url || appUrl(`/join/${invite?.invite_code ?? r.invite_code}`);
  const code = invite?.invite_code ?? r.invite_code;

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      toast.success("Invite link copied");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Couldn't copy. Select the link and copy it manually.");
    }
  }

  return (
    <div className="min-w-0 space-y-4">
      <Card>
        <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h2 className="text-xl font-semibold tracking-tight">{r.name}</h2>
            {r.description && <p className="mt-1 text-sm text-muted-foreground">{r.description}</p>}
            <p className="mt-2 text-xs text-subtle">Created {dateTime(r.created_at)}</p>
          </div>
          <Button asChild>
            <Link href={`/chat/${r.id}`}>
              <MessagesSquare /> Open chat
            </Link>
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Link2 className="size-4 text-primary" /> Invite people
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {inviteError && !invite ? (
            <p className="text-sm text-danger">{inviteError}</p>
          ) : !invite ? (
            <Skeleton className="h-10 w-full" />
          ) : (
            <>
              <div className="flex gap-2">
                <Input readOnly value={inviteUrl} onFocus={(e) => e.currentTarget.select()} aria-label="Invite link" className="tabular-nums text-[13px]" />
                <Button variant="secondary" onClick={() => copy(inviteUrl)} aria-label="Copy invite link">
                  {copied ? <Check className="text-primary" /> : <Copy />}
                  <span className="hidden sm:inline">{copied ? "Copied" : "Copy"}</span>
                </Button>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Button asChild variant="secondary">
                  <a href={invite.whatsapp_url || whatsappUrl(roomInviteText(r.name, inviteUrl))} target="_blank" rel="noopener noreferrer">
                    <MessageCircle className="text-[#25D366]" /> Share on WhatsApp
                  </a>
                </Button>
                <p className="text-sm text-muted-foreground">
                  Or share code <span className="rounded-md bg-muted px-1.5 py-0.5 tabular-nums text-foreground">{code}</span>
                </p>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Members</CardTitle>
          <span className="text-xs text-muted-foreground">{r.members?.length ?? r.member_count}</span>
        </CardHeader>
        <CardContent>
          {!r.members?.length ? (
            <p className="text-sm text-muted-foreground">Member details aren&apos;t available for this room.</p>
          ) : (
            <ul className="divide-y divide-border">
              {r.members.map((m) => (
                <li key={m.id} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
                  <UserAvatar id={m.user_id} name={m.name} online={m.online} className="size-9 text-[12px] ring-0" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{m.name}</p>
                    <p className="truncate text-xs text-subtle">{m.email}</p>
                  </div>
                  {m.role === "owner" || m.role === "admin" ? (
                    <Badge tone="primary">
                      <Crown /> {m.role}
                    </Badge>
                  ) : (
                    <span className="text-xs text-subtle">joined {relativeTime(m.joined_at)}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
