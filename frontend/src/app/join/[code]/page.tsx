"use client";

import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Logo } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** Target of shared invite links: /join/CODE. Logs in first if needed, then joins. */
export default function JoinPage() {
  const { code } = useParams<{ code: string }>();
  const { status } = useAuth();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (status === "anonymous") router.replace(`/register?next=${encodeURIComponent(`/join/${code}`)}`);
    if (status !== "authenticated" || started.current) return;
    started.current = true;
    api.rooms
      .join(decodeURIComponent(code))
      .then((room) => router.replace(`/chat/${room.id}`))
      .catch((e) => setError(e instanceof Error ? e.message : "Could not join this room"));
  }, [status, code, router]);

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-8 px-4">
      <Logo />
      <Card className="w-full max-w-sm p-6 text-center">
        {error ? (
          <>
            <p className="font-medium">Couldn&apos;t join</p>
            <p className="mt-1 text-sm text-muted-foreground">{error}</p>
            <Button asChild className="mt-5" variant="secondary">
              <Link href="/rooms">Go to my rooms</Link>
            </Button>
          </>
        ) : (
          <p className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Joining room…
          </p>
        )}
      </Card>
    </div>
  );
}
