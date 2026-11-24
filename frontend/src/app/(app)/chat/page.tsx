"use client";

import { LogIn, MessagesSquare, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { PageContainer } from "@/components/app-shell";
import { EmptyState, ErrorState, LoadingList, PageHeader } from "@/components/common";
import { useRooms } from "@/components/rooms/rooms-context";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export default function ChatIndexPage() {
  const { rooms, loading, error, reload, openCreate, openJoin } = useRooms();
  const router = useRouter();

  // Desktop has the room list in the sidebar, so jump straight into the most recent room.
  useEffect(() => {
    if (rooms.length && window.matchMedia("(min-width: 1024px)").matches) router.replace(`/chat/${rooms[0].id}`);
  }, [rooms, router]);

  return (
    <PageContainer className="max-w-2xl">
      <PageHeader
        title="Conversations"
        actions={
          <>
            <Button variant="secondary" onClick={openJoin}>
              <LogIn /> Join
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
        <EmptyState icon={MessagesSquare} title="No conversations yet" description="Create a room for your family or friends, or join one with an invite code." />
      ) : (
        <div className="space-y-2">
          {rooms.map((r) => (
            <Link key={r.id} href={`/chat/${r.id}`} className="block">
              <Card className="flex items-center gap-3 p-4 transition-colors hover:border-border-strong">
                <span className="grid size-10 place-items-center rounded-[10px] bg-muted font-semibold">{r.name[0]?.toUpperCase()}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{r.name}</p>
                  <p className="text-xs text-muted-foreground">{r.member_count} members · @Nazar</p>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </PageContainer>
  );
}
