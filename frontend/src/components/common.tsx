import { AlertTriangle, Briefcase, Inbox, Plane, RefreshCw, TrendingUp, Search } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, Skeleton } from "@/components/ui/card";
import type { WatchStatus, WatchType } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Brand mark: a simple eye on deep emerald. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-7", className)} aria-hidden>
      <rect width="32" height="32" rx="8" fill="#0B7A5A" />
      <path d="M6 16c2.8-4.6 6.2-6.9 10-6.9s7.2 2.3 10 6.9c-2.8 4.6-6.2 6.9-10 6.9S8.8 20.6 6 16Z" fill="none" stroke="#fff" strokeWidth="1.9" strokeLinejoin="round" />
      <circle cx="16" cy="16" r="3.4" fill="#fff" />
    </svg>
  );
}

export function Logo({ href = "/", className }: { href?: string; className?: string }) {
  return (
    <Link href={href} className={cn("flex items-center gap-2", className)}>
      <LogoMark />
      <span className="text-[15px] font-semibold tracking-[-0.02em]">Nazar Rakho</span>
    </Link>
  );
}

export function NazarAvatar({ className }: { className?: string }) {
  return (
    <div className={cn("grid size-8 shrink-0 place-items-center rounded-full bg-primary", className)}>
      <svg viewBox="0 0 24 24" className="size-[17px]" aria-hidden>
        <path d="M3 12c2.2-3.7 5.2-5.5 9-5.5s6.8 1.8 9 5.5c-2.2 3.7-5.2 5.5-9 5.5S5.2 15.7 3 12Z" fill="none" stroke="#fff" strokeWidth="1.8" />
        <circle cx="12" cy="12" r="2.6" fill="#fff" />
      </svg>
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-[26px] font-semibold tracking-[-0.025em]">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function LoadingList({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-3", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Card key={i} className="space-y-3 p-5">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-3 w-2/3" />
          <Skeleton className="h-3 w-1/2" />
        </Card>
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Card className="flex flex-col items-center gap-3 border-danger/20 px-6 py-10 text-center">
      <AlertTriangle className="size-6 text-danger" />
      <p className="max-w-sm text-sm text-muted-foreground">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          <RefreshCw /> Try again
        </Button>
      )}
    </Card>
  );
}

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <Card className="flex flex-col items-center gap-3 border-dashed bg-transparent px-6 py-14 text-center">
      <div className="grid size-10 place-items-center rounded-full bg-muted">
        <Icon className="size-5 text-muted-foreground" />
      </div>
      <div>
        <p className="font-medium">{title}</p>
        {description && <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">{description}</p>}
      </div>
      {action}
    </Card>
  );
}

export const WATCH_ICON: Record<WatchType, React.ComponentType<{ className?: string }>> = {
  flight: Plane,
  stock: TrendingUp,
  job_notification: Briefcase,
  topic: Search,
};

/**
 * One soft color per meaning, used everywhere so colors stay readable:
 * emerald = watching/brand, sky = alerts & flights, amber = attention & stocks, violet = rooms & jobs.
 */
export const TONES = {
  emerald: { soft: "bg-[#ecfdf5] text-[#047857]", solid: "bg-[#059669]", ring: "ring-[#a7f3d0]", text: "text-[#047857]", wash: "from-[#ecfdf5]" },
  sky: { soft: "bg-[#eff6ff] text-[#1d4ed8]", solid: "bg-[#3b82f6]", ring: "ring-[#bfdbfe]", text: "text-[#1d4ed8]", wash: "from-[#eff6ff]" },
  amber: { soft: "bg-[#fffbeb] text-[#b45309]", solid: "bg-[#f59e0b]", ring: "ring-[#fde68a]", text: "text-[#b45309]", wash: "from-[#fffbeb]" },
  violet: { soft: "bg-[#f5f3ff] text-[#6d28d9]", solid: "bg-[#8b5cf6]", ring: "ring-[#ddd6fe]", text: "text-[#6d28d9]", wash: "from-[#f5f3ff]" },
  rose: { soft: "bg-[#fff1f2] text-[#be123c]", solid: "bg-[#f43f5e]", ring: "ring-[#fecdd3]", text: "text-[#be123c]", wash: "from-[#fff1f2]" },
} as const;
export type Tone = keyof typeof TONES;

export const WATCH_TONE: Record<WatchType, Tone> = { flight: "sky", stock: "amber", job_notification: "violet", topic: "rose" };

export function WatchTypeIcon({ type, className }: { type: WatchType; className?: string }) {
  const Icon = WATCH_ICON[type] ?? Inbox;
  return (
    <div className={cn("grid size-9 shrink-0 place-items-center rounded-[10px]", TONES[WATCH_TONE[type] ?? "emerald"].soft, className)}>
      <Icon className="size-[17px]" />
    </div>
  );
}

/** Deterministic room/person color from an id. */
export function toneFor(id: number | string): Tone {
  const order: Tone[] = ["emerald", "sky", "violet", "amber", "rose"];
  return order[Math.abs(Number(String(id).replace(/\D/g, "")) || String(id).length) % order.length];
}

export function StatusBadge({ status }: { status: WatchStatus | string }) {
  const map: Record<string, { dot: string; label: string }> = {
    active: { dot: "bg-primary", label: "Active" },
    paused: { dot: "bg-[#d4a017]", label: "Paused" },
    completed: { dot: "bg-subtle", label: "Done" },
    failed: { dot: "bg-danger", label: "Failed" },
    deleted: { dot: "bg-subtle", label: "Deleted" },
  };
  const s = map[status] ?? { dot: "bg-subtle", label: status };
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-[12px] text-muted-foreground">
      <span className={cn("size-1.5 rounded-full", s.dot)} />
      {s.label}
    </span>
  );
}
