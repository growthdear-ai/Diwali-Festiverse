"use client";

import { Loader2 } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { AlertNotifier } from "@/components/alerts/alert-notifier";
import { AppShell } from "@/components/app-shell";
import { LogoMark } from "@/components/common";

export function Splash() {
  return (
    <div className="grid h-dvh place-items-center">
      <div className="flex flex-col items-center gap-3 text-sm text-muted-foreground">
        <LogoMark className="size-10" />
        <Loader2 className="size-4 animate-spin" />
      </div>
    </div>
  );
}
import { RoomsProvider } from "@/components/rooms/rooms-context";
import { disconnectNexconn } from "@/chat/nexconn";
import { useAuth } from "@/lib/auth";

export function AppGate({ children }: { children: React.ReactNode }) {
  const { status, expired } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status !== "anonymous") return;
    disconnectNexconn();
    const q = new URLSearchParams({ next: pathname });
    if (expired) q.set("expired", "1");
    router.replace(`/login?${q}`);
  }, [status, expired, pathname, router]);

  if (status !== "authenticated") return <Splash />;

  return (
    <RoomsProvider>
      <AlertNotifier />
      <AppShell>{children}</AppShell>
    </RoomsProvider>
  );
}
