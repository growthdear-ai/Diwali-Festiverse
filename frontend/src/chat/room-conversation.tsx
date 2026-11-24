"use client";

import { Loader2, WifiOff } from "lucide-react";
import { createElement, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { MemberNamesProvider } from "@/components/alerts/alert-card";
import { ChatMessage, clock, DateSeparator, MessageComposer, type MentionTarget } from "@/components/chat/chat-parts";
import { ErrorState, NazarAvatar } from "@/components/common";
import { BotMessage, isSilentBotReply, toBotPayload } from "@/components/nazar/bot-message";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toDate } from "@/lib/format";
import type { ChatMessage as ChatMessageT, Member, Room } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";
import { connectNexconn, nexconnAvailable, openGroup } from "./nexconn";

export type ChatMode = "nexconn" | "relay";

let tempId = 0; // negative ids mark optimistic, unsent messages

/** Why Nexconn can't be used for this room, or null when it can. */
export function nexconnBlocker(room: Room, nexconnToken?: string | null): string | null {
  if (!nexconnAvailable()) return "NEXT_PUBLIC_NEXCONN_APP_KEY is not set";
  if (!nexconnToken) return "the backend did not issue a Nexconn user token";
  if (!room.nexconn_conversation_id) return "this room has no Nexconn group yet";
  return null;
}

interface Props {
  room: Room;
  rooms: Room[];
  members: Member[];
  /** In-room message search (relay mode; Nexconn ChatUI has its own UI). */
  search?: string;
  /** Called after Nazar replies (e.g. a watch was created) so side panels can refresh. */
  onActivity?: () => void;
  onModeChange?: (mode: ChatMode, reason: string | null) => void;
}

/** Chat adapter: Nexconn ChatUI when configured, backend message relay otherwise. Same props either way. */
export function RoomConversation({ room, rooms, members, search, onActivity, onModeChange }: Props) {
  const { user } = useAuth();
  const [forceRelay, setForceRelay] = useState(false);
  const blocker = nexconnBlocker(room, user?.nexconn_token);
  const mode: ChatMode = blocker || forceRelay ? "relay" : "nexconn";

  useEffect(() => {
    onModeChange?.(mode, forceRelay ? "Nexconn connection failed" : blocker);
  }, [mode, blocker, forceRelay, onModeChange]);

  if (mode === "nexconn")
    return <NexconnConversation key={room.id} room={room} rooms={rooms} members={members} onFallback={() => setForceRelay(true)} />;
  return <RelayConversation key={room.id} room={room} members={members} search={search} onActivity={onActivity} />;
}

function NexconnConversation({ room, rooms, members, onFallback }: Omit<Props, "onModeChange" | "search" | "onActivity"> & { onFallback: () => void }) {
  const { user } = useAuth();
  const [state, setState] = useState<"connecting" | "ready" | "error">("connecting");
  const [error, setError] = useState("");
  const membersRef = useRef(members);
  const roomsRef = useRef(rooms);
  useEffect(() => {
    membersRef.current = members;
    roomsRef.current = rooms;
  });

  useEffect(() => {
    if (!user?.nexconn_token || !room.nexconn_conversation_id) return;
    let live = true;
    connectNexconn(user.nexconn_token, {
      currentUser: { userId: user.nexconn_user_id || String(user.id), name: user.name },
      group: (gid) => {
        const r = roomsRef.current.find((x) => x.nexconn_conversation_id === gid);
        return r ? { name: r.name, memberCount: r.member_count } : null;
      },
      members: async (gid) => {
        const r = roomsRef.current.find((x) => x.nexconn_conversation_id === gid);
        const list = r?.id === room.id ? membersRef.current : r ? ((await api.rooms.get(r.id)).members ?? []) : [];
        return list.map((m) => ({ userId: m.nexconn_user_id || String(m.user_id), name: m.name }));
      },
    })
      .then(() => openGroup(room.nexconn_conversation_id!))
      .then(() => live && setState("ready"))
      .catch((e: unknown) => {
        if (!live) return;
        setError(e instanceof Error ? e.message : "Could not connect to Nexconn.");
        setState("error");
      });
    return () => {
      live = false;
    };
  }, [room.id, room.nexconn_conversation_id, user?.nexconn_token, user?.nexconn_user_id, user?.id, user?.name]);

  if (state === "error")
    return (
      <div className="grid h-full place-items-center p-6">
        <div className="max-w-md space-y-3 text-center">
          <ErrorState message={error} />
          <Button variant="secondary" size="sm" onClick={onFallback}>
            <WifiOff /> Continue with backend relay
          </Button>
        </div>
      </div>
    );

  return (
    <div className="relative h-full">
      {state === "connecting" && (
        <div className="absolute inset-0 z-10 grid place-items-center bg-background/80">
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Connecting to Nexconn…
          </p>
        </div>
      )}
      {/* Nexconn ChatUI's conversation panel: header, history, input, @mentions, images. */}
      <div className="nexconn-host">{state === "ready" && createElement("nc-channel-detail-provider")}</div>
    </div>
  );
}

function RelayConversation({ room, members, search, onActivity }: { room: Room; members: Member[]; search?: string; onActivity?: () => void }) {
  const { user } = useAuth();
  const { data, error, loading, reload, setData } = useApi(() => api.messages.list(room.id), [room.id], { pollMs: 5000 });
  const [sending, setSending] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  const names = useMemo(() => new Map(members.map((m) => [m.user_id, m.name])), [members]);
  const voterNames = useMemo(() => ({ meId: user?.id, names: new Map(members.map((m) => [String(m.user_id), m.name])) }), [members, user?.id]);
  const mentionables = useMemo<MentionTarget[]>(
    () => [{ id: "nazar", name: "Nazar", bot: true }, ...members.filter((m) => m.user_id !== user?.id).map((m) => ({ id: String(m.user_id), name: m.name, bot: false }))],
    [members, user?.id],
  );
  const q = search?.trim().toLowerCase() ?? "";
  // Keep a local fallback for older backends that don't persist Nazar's room reply.
  const [localBot, setLocalBot] = useState<ChatMessageT[]>([]);
  const all = useMemo(
    () => [...(data ?? []), ...localBot].sort((a, b) => (toDate(a.created_at)?.getTime() ?? 0) - (toDate(b.created_at)?.getTime() ?? 0)),
    [data, localBot],
  );
  const messages = q ? all.filter((m) => m.message_type === "text" && m.message_text.toLowerCase().includes(q)) : all;
  const lastId = all.at(-1)?.id;

  useEffect(() => {
    if (!q) listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [lastId, q]);

  const [thinking, setThinking] = useState(false);

  async function send(raw: string) {
    // The backend only answers "@nazar"; people often type "Nazar …" or "hey nazar …", so add the @.
    const body = raw.replace(/^(?:(hey|hi|hello)\s+)?nazar\b[,:]?/i, (_, greet: string | undefined) => (greet ? `${greet} @Nazar` : "@Nazar"));
    const asksNazar = /@nazar\b/i.test(body);
    setSending(true);
    setThinking(asksNazar);
    const temp: ChatMessageT = { id: --tempId, room_id: room.id, sender_id: user?.id ?? null, message_text: body, message_type: "text", created_at: new Date().toISOString() };
    setData((prev) => [...(prev ?? []), temp]);
    try {
      const res = await api.messages.send(room.id, body);
      const fresh = await api.messages.list(room.id);
      setData(fresh);
      if (res?.bot_reply && !isSilentBotReply(res.bot_reply)) {
        // Newer backends store Nazar's reply as a room message; only keep a local copy when it wasn't stored.
        const stored = fresh.some((m) => m.sender_id === null && m.id > (res.message?.id ?? 0));
        if (!stored) {
          const at = new Date((toDate(res.message?.created_at)?.getTime() ?? Date.now()) + 1).toISOString();
          setLocalBot((prev) => [...prev, { id: 1_000_000_000 + prev.length, room_id: room.id, sender_id: null, message_text: JSON.stringify(res.bot_reply), message_type: "bot", created_at: at }]);
        }
        onActivity?.();
      }
      return true;
    } catch (e) {
      setData((prev) => prev?.filter((m) => m.id !== temp.id));
      toast.error(e instanceof Error ? e.message : "Message not sent");
      return false;
    } finally {
      setSending(false);
      setThinking(false);
    }
  }

  return (
    <MemberNamesProvider value={voterNames}>
      <div className="flex h-full flex-col">
        <div ref={listRef} className="scrollbar-thin flex-1 overflow-y-auto px-3 py-4 sm:px-6">
          {loading && !data ? (
            <div className="space-y-4">
              {[0, 1, 2].map((i) => (
                <div key={i} className={cn("flex gap-3", i === 1 && "justify-end")}>
                  <Skeleton className={cn("h-14 rounded-2xl", i === 1 ? "w-1/3" : "w-1/2")} />
                </div>
              ))}
            </div>
          ) : error && !data ? (
            <ErrorState message={error} onRetry={reload} />
          ) : q && messages.length === 0 ? (
            <p className="py-16 text-center text-sm text-muted-foreground">No messages match “{search}”.</p>
          ) : all.length === 0 ? (
            <EmptyChat />
          ) : (
            <div className="mx-auto max-w-3xl">
              {messages.map((m, i) => {
                const isBotMsg = (x: ChatMessageT) => x.sender_id === null || (x.message_type !== "text" && x.sender_id !== user?.id);
                const d = toDate(m.created_at) ?? new Date();
                const prev = messages[i - 1];
                const sep = !prev || (toDate(prev.created_at) ?? new Date()).toDateString() !== d.toDateString() ? <DateSeparator date={d} /> : null;
                const isBot = isBotMsg(m);
                const grouped = !sep && !isBot && !!prev && !isBotMsg(prev) && prev.sender_id === m.sender_id;
                return (
                  <div key={m.id}>
                    {sep}
                    {isBot ? (
                      <div className="mt-4">
                        <BotMessage payload={{ ...toBotPayload(m.message_text), created_at: m.created_at }} />
                      </div>
                    ) : (
                      <ChatMessage
                        text={m.message_text}
                        name={m.sender_name || names.get(m.sender_id!) || "Member"}
                        senderId={m.sender_id ?? 0}
                        mine={m.sender_id === user?.id}
                        time={clock(m.created_at)}
                        pending={m.id < 0}
                        grouped={grouped}
                        query={q || undefined}
                      />
                    )}
                  </div>
                );
              })}
              {thinking && (
                <div className="mt-4 flex items-center gap-2.5" role="status" aria-live="polite">
                  <NazarAvatar className="size-7" />
                  <span className="inline-flex items-center gap-1 rounded-[18px] rounded-tl-[6px] bg-muted px-3.5 py-2.5 text-[13px] text-muted-foreground">
                    Nazar is thinking
                    <span className="inline-flex gap-0.5" aria-hidden>
                      <span className="size-1 animate-bounce rounded-full bg-subtle [animation-delay:-0.3s]" />
                      <span className="size-1 animate-bounce rounded-full bg-subtle [animation-delay:-0.15s]" />
                      <span className="size-1 animate-bounce rounded-full bg-subtle" />
                    </span>
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
        <MessageComposer onSend={send} sending={sending} mentionables={mentionables} />
      </div>
    </MemberNamesProvider>
  );
}

function EmptyChat() {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center py-12 text-center">
      <NazarAvatar className="size-12" />
      <p className="mt-4 font-semibold">Nazar is in the room</p>
      <p className="mt-1 text-sm text-muted-foreground">Mention @Nazar for a quick web search, or ask it to watch something and post here when it changes.</p>
      <div className="mt-5 w-full space-y-2 text-left text-[13px] text-muted-foreground">
        {["@Nazar phones under 60000", "@Nazar Delhi se Mumbai 12 Dec ka flight 4000 se kam ho toh batao", "@Nazar track SSC CGL notification"].map((e) => (
          <p key={e} className="rounded-[10px] border border-border bg-surface px-3 py-2">
            {e}
          </p>
        ))}
      </div>
    </div>
  );
}
