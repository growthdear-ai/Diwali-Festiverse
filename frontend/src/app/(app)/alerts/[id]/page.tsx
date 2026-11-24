"use client";

import { ArrowLeft, MessagesSquare } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect } from "react";
import { PageContainer } from "@/components/app-shell";
import { ErrorState, LoadingList } from "@/components/common";
import { AlertCard } from "@/components/alerts/alert-card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";
import { useApi } from "@/lib/use-api";

export default function AlertDetailPage() {
  const { id } = useParams<{ id: string }>();
  const alertId = Number(id);
  const { markRead } = usePrefs();
  const alert = useApi(() => api.alerts.get(alertId), [alertId]);
  const watchId = alert.data?.watch_id;
  const watch = useApi(() => (watchId ? api.watches.get(watchId) : Promise.resolve(null)), [watchId]);

  useEffect(() => {
    if (alert.data) markRead(alert.data.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alert.data?.id]);

  return (
    <PageContainer className="max-w-2xl">
      <div className="mb-4 flex items-center justify-between">
        <Link href="/alerts" className="inline-flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" /> Alerts
        </Link>
        {alert.data && (
          <Button variant="secondary" size="sm" asChild>
            <Link href={`/chat/${alert.data.room_id}`}>
              <MessagesSquare /> Discuss in room
            </Link>
          </Button>
        )}
      </div>
      {alert.error && !alert.data ? (
        <ErrorState message={alert.error} onRetry={alert.reload} />
      ) : !alert.data || (watchId && watch.loading) ? (
        <LoadingList rows={1} />
      ) : (
        <AlertCard alert={alert.data} watch={watch.data} className="max-w-none" />
      )}
    </PageContainer>
  );
}
