"use client";

import { createContext, useContext, useState } from "react";
import { api } from "@/lib/api";
import type { Room } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { CreateRoomModal, JoinRoomDialog } from "./room-dialogs";

interface RoomsContextValue {
  rooms: Room[];
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
  upsert: (room: Room) => void;
  openCreate: () => void;
  openJoin: () => void;
}

const RoomsContext = createContext<RoomsContextValue | null>(null);

export function RoomsProvider({ children }: { children: React.ReactNode }) {
  const { data, loading, error, reload, setData } = useApi(() => api.rooms.list(), [], { pollMs: 30_000 });
  const [dialog, setDialog] = useState<"create" | "join" | null>(null);

  const upsert = (room: Room) => setData((prev) => [room, ...(prev ?? []).filter((r) => r.id !== room.id)]);

  return (
    <RoomsContext.Provider
      value={{ rooms: data ?? [], loading, error, reload, upsert, openCreate: () => setDialog("create"), openJoin: () => setDialog("join") }}
    >
      {children}
      <CreateRoomModal open={dialog === "create"} onOpenChange={(o) => setDialog(o ? "create" : null)} onCreated={upsert} />
      <JoinRoomDialog open={dialog === "join"} onOpenChange={(o) => setDialog(o ? "join" : null)} onJoined={upsert} />
    </RoomsContext.Provider>
  );
}

export function useRooms() {
  const ctx = useContext(RoomsContext);
  if (!ctx) throw new Error("useRooms must be used inside <RoomsProvider>");
  return ctx;
}
