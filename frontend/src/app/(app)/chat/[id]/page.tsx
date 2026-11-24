"use client";

import { useParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { RoomHeader, RoomSidePanel } from "@/components/chat/room-panels";
import { ErrorState, LoadingList } from "@/components/common";
import { useRooms } from "@/components/rooms/rooms-context";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { WatchDialog } from "@/components/watches/watch-dialog";
import { RoomConversation, type ChatMode } from "@/chat/room-conversation";
import { api } from "@/lib/api";
import { toDate } from "@/lib/format";
import { useApi } from "@/lib/use-api";

export default function ChatRoomPage() {
  const { id } = useParams<{ id: string }>();
  const roomId = Number(id);
  const { rooms } = useRooms();
  const room = useApi(() => api.rooms.get(roomId), [roomId]);
  const watches = useApi(() => api.watches.list({ room_id: roomId }), [roomId], { pollMs: 60_000 });
  const alerts = useApi(() => api.alerts.list({ room_id: roomId }), [roomId], { pollMs: 60_000 });
  const [panelOpen, setPanelOpen] = useState(false);
  const [newWatch, setNewWatch] = useState(false);
  const [search, setSearch] = useState("");
  const [mode, setMode] = useState<{ mode: ChatMode; reason: string | null } | null>(null);
  const onModeChange = useCallback((m: ChatMode, reason: string | null) => setMode({ mode: m, reason }), []);

  const roomWatches = (watches.data ?? []).filter((w) => w.room_id === roomId && w.status !== "deleted");
  const roomAlerts = useMemo(
    () => (alerts.data ?? []).filter((a) => a.room_id === roomId).sort((a, b) => (toDate(b.created_at)?.getTime() ?? 0) - (toDate(a.created_at)?.getTime() ?? 0)),
    [alerts.data, roomId],
  );
  const members = room.data?.members ?? [];

  if (room.error && !room.data)
    return (
      <div className="grid h-full place-items-center p-6">
        <ErrorState message={room.error} onRetry={room.reload} />
      </div>
    );

  const panel = (
    <RoomSidePanel
      watches={roomWatches}
      alerts={roomAlerts}
      loading={watches.loading && !watches.data}
      error={watches.error}
      onRetry={watches.reload}
      onNew={() => {
        setPanelOpen(false);
        setNewWatch(true);
      }}
    />
  );

  return (
    <div className="flex h-full">
      <section className="flex min-w-0 flex-1 flex-col">
        <RoomHeader room={room.data} members={members} mode={mode} search={search} onSearch={setSearch} watchCount={roomWatches.filter((w) => w.status !== "completed").length} onOpenPanel={() => setPanelOpen(true)} />
        <div className="min-h-0 flex-1">
          {room.data ? <RoomConversation room={room.data} rooms={rooms} members={members} search={search} onActivity={() => (watches.reload(), alerts.reload())} onModeChange={onModeChange} /> : <LoadingList rows={2} className="p-6" />}
        </div>
      </section>

      <aside className="hidden w-[340px] shrink-0 border-l border-border bg-background xl:block">{panel}</aside>

      <Dialog open={panelOpen} onOpenChange={setPanelOpen}>
        <DialogContent side="right" className="w-[min(360px,92vw)] p-0">
          <DialogTitle className="sr-only">Room watches and alerts</DialogTitle>
          {panel}
        </DialogContent>
      </Dialog>

      <WatchDialog
        open={newWatch}
        onOpenChange={setNewWatch}
        rooms={rooms}
        roomId={roomId}
        onSaved={(w) => watches.setData((prev) => [w, ...(prev ?? []).filter((x) => x.id !== w.id)])}
      />
    </div>
  );
}
