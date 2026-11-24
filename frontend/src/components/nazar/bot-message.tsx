"use client";

import { ArrowUpRight } from "lucide-react";
import { useEffect, useState } from "react";
import { AlertCard } from "@/components/alerts/alert-card";
import { NazarAvatar } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { money, relativeTime, targetCondition, watchTitle } from "@/lib/format";
import type { Alert, Watch } from "@/lib/types";
import { cn } from "@/lib/utils";

export type BotKind =
  | "watch_activated"
  | "watch_paused"
  | "watch_resumed"
  | "watch_failed"
  | "new_alert"
  | "research"
  | "verified_notice"
  | "flagged_notice";

export interface BotPayload {
  kind?: BotKind | string;
  text?: string;
  alert_id?: number;
  alert?: Alert;
  watch_id?: number;
  watch?: Watch;
  error?: string;
  sources?: { title?: string; url?: string }[];
  results?: SearchResult[];
  follow_up_question?: string;
  created_at?: string;
}

export interface SearchResult {
  title: string;
  url?: string | null;
  source?: string;
  snippet?: string;
  price?: number | null;
  currency?: string;
  action_label?: string;
}

/** Accepts a parsed object or a JSON string; plain text becomes a research message. */
/** Backend bot `action` values → presentation kinds. */
const ACTION_KIND: Record<string, BotKind> = {
  watch_created: "watch_activated",
  watch_rejected: "watch_failed",
  watch_paused: "watch_paused",
  watch_resumed: "watch_resumed",
};

/** Emoji read as noise in a calm UI; strip them (and leftover joiners/indent) from bot text. */
const stripEmoji = (t?: string) =>
  t
    ?.replace(/[\p{Extended_Pictographic}\u{FE0F}\u{200D}]/gu, "")
    .replace(/^[ \t]+/gm, "")
    .trim();

export function toBotPayload(raw: unknown): BotPayload {
  if (typeof raw === "string") {
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") return toBotPayload(parsed);
    } catch {}
    return { kind: "research", text: stripEmoji(raw) };
  }
  const o = (raw ?? {}) as Record<string, unknown>;
  const action = typeof o.action === "string" ? o.action : undefined;
  const kind = (o.kind ?? o.type ?? o.event ?? (action ? ACTION_KIND[action] : undefined)) as string | undefined;
  const text = (o.summary ?? o.text ?? o.reply) as string | undefined;
  return {
    ...(o as BotPayload),
    text: stripEmoji(text),
    error: typeof o.error === "string" ? o.error : undefined,
    kind: kind ?? (o.alert || o.alert_id ? "new_alert" : "research"),
  };
}

/** Backend replies with nothing to show (e.g. a message that didn't mention Nazar). */
export function isSilentBotReply(raw: unknown) {
  const o = raw as Record<string, unknown> | null;
  return !o || o.action === "ignored" || (!o.reply && !o.text && !o.alert_id && !o.watch_id);
}

const EVENTS: Record<string, { label: string }> = {
  watch_activated: { label: "Watch activated" },
  watch_paused: { label: "Watch paused" },
  watch_resumed: { label: "Watch resumed" },
  watch_failed: { label: "Watch check failed" },
};

function useEntity<T>(id: number | undefined, embedded: T | undefined, fetcher: (id: number) => Promise<T>) {
  const [data, setData] = useState<T | undefined>(embedded);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (embedded || !id) return;
    let live = true;
    fetcher(id)
      .then((d) => live && setData(d))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, embedded]);
  return { data, failed };
}

function Shell({ children, time }: { children: React.ReactNode; time?: string }) {
  return (
    <div className="flex w-full max-w-[560px] gap-2.5">
      <NazarAvatar className="mt-5 size-7" />
      <div className="min-w-0 flex-1">
        <p className="mb-1 px-1 text-[12px] text-muted-foreground">
          <span className="font-medium text-foreground">Nazar</span>
          {time && <span> · {relativeTime(time)}</span>}
        </p>
        {children}
      </div>
    </div>
  );
}

function WatchEvent({ payload }: { payload: BotPayload }) {
  const meta = EVENTS[payload.kind as string];
  const { data: watch } = useEntity(payload.watch_id, payload.watch, api.watches.get);
  const failed = payload.kind === "watch_failed";
  return (
    <Shell time={payload.created_at}>
      <div className="inline-block max-w-full rounded-[18px] rounded-tl-[6px] bg-muted px-3.5 py-2.5 text-[14px] leading-relaxed">
        {payload.text ? (
          <p className={cn(failed && "text-danger")}>{payload.text}</p>
        ) : (
          <p>
            <span className={cn("font-medium", failed && "text-danger")}>{meta.label}.</span>{" "}
            {watch && `${watchTitle(watch.rule_json)}, ${targetCondition(watch.rule_json).toLowerCase()}.`}
          </p>
        )}
        {payload.error && <p className="mt-1 text-danger">{payload.error}</p>}
        {watch && (
          <a href={`/watches/${watch.id}`} className="mt-1 inline-block text-[13px] text-primary underline-offset-4 hover:underline">
            Open watch
          </a>
        )}
      </div>
    </Shell>
  );
}

function AlertMessage({ payload }: { payload: BotPayload }) {
  const { data: alert, failed } = useEntity(payload.alert_id, payload.alert, api.alerts.get);
  const { data: watch } = useEntity(alert?.watch_id, undefined, api.watches.get);

  if (failed) return <Research payload={{ text: payload.text || "This alert is no longer available." }} />;
  if (!alert)
    return (
      <div className="w-full max-w-[520px] space-y-3 rounded-[16px] border border-border bg-surface p-5">
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-5 w-3/4" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  return (
    <div className="w-full max-w-[560px]">
      <AlertCard alert={alert} watch={watch} key={watch?.id ?? "nowatch"} />
    </div>
  );
}

function Research({ payload }: { payload: BotPayload }) {
  const results = payload.results?.filter((result) => result.title).slice(0, 5) ?? [];
  const resultUrls = new Set(results.map((result) => result.url).filter(Boolean));
  const additionalSources = payload.sources?.filter((source) => source.url && !resultUrls.has(source.url)) ?? [];
  return (
    <Shell time={payload.created_at}>
      <div className="w-full max-w-full rounded-[18px] rounded-tl-[6px] bg-muted p-3.5">
        {payload.text && <p className="whitespace-pre-line text-[14px] leading-relaxed">{payload.text}</p>}
        {results.length > 0 && (
          <div className="mt-3 space-y-2">
            {results.map((result, index) => {
              const href = result.url && /^https?:\/\//i.test(result.url) ? result.url : null;
              return (
                <article key={`${result.url ?? result.title}-${index}`} className="rounded-xl border border-border bg-background/80 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      {href ? (
                        <a href={href} target="_blank" rel="noopener noreferrer" className="font-medium leading-snug text-foreground underline-offset-4 hover:text-primary hover:underline">
                          {result.title}
                        </a>
                      ) : (
                        <p className="font-medium leading-snug text-foreground">{result.title}</p>
                      )}
                      {result.source && <p className="mt-1 text-[11px] text-muted-foreground">{result.source}</p>}
                    </div>
                    {typeof result.price === "number" && (
                      <span className="shrink-0 text-[14px] font-semibold tabular-nums">
                        {money(result.price, result.currency || "INR")}
                      </span>
                    )}
                  </div>
                  {result.snippet && <p className="mt-1.5 text-[12px] leading-relaxed text-muted-foreground">{result.snippet}</p>}
                  {href && result.action_label && (
                    <Button
                      className="mt-2"
                      size="sm"
                      variant={/book|ticket/i.test(result.action_label) ? "default" : "secondary"}
                      asChild
                    >
                      <a href={href} target="_blank" rel="noopener noreferrer">
                        {result.action_label} <ArrowUpRight aria-hidden />
                      </a>
                    </Button>
                  )}
                </article>
              );
            })}
          </div>
        )}
        {payload.follow_up_question && (
          <p className="mt-3 text-[13px] font-medium text-foreground">{payload.follow_up_question}</p>
        )}
        {additionalSources.map((s, i) =>
          s.url && /^https?:\/\//i.test(s.url) ? (
            <a key={i} href={s.url} target="_blank" rel="noopener noreferrer" className="mt-2 block truncate text-[12px] text-primary underline-offset-4 hover:underline">
              {s.title || s.url}
            </a>
          ) : null,
        )}
      </div>
    </Shell>
  );
}

export function BotMessage({ payload }: { payload: BotPayload }) {
  if (payload.kind && payload.kind in EVENTS) return <WatchEvent payload={payload} />;
  if (payload.kind === "new_alert" || payload.kind === "verified_notice" || payload.kind === "flagged_notice" || payload.alert || payload.alert_id)
    return <AlertMessage payload={payload} />;
  return <Research payload={payload} />;
}
