"use client";

import { ArrowUpRight, Check, ShieldAlert, ShieldCheck } from "lucide-react";
import { createContext, useContext, useState } from "react";
import { toast } from "sonner";
import { NazarAvatar } from "@/components/common";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { dateTime, relativeTime, targetCondition, WATCH_TYPE_LABEL } from "@/lib/format";
import type { Alert, VoteChoice, VoteSummary, Watch, WatchType } from "@/lib/types";
import { cn } from "@/lib/utils";
import { alertShareText, whatsappUrl } from "@/lib/whatsapp";

/* Lets cards name voters ("Mummy and Papa voted Yes") when rendered inside a room. */
interface MemberNames {
  meId?: number;
  names: Map<string, string>;
}
const MemberNamesContext = createContext<MemberNames>({ names: new Map() });
export function MemberNamesProvider({ value, children }: { value: MemberNames; children: React.ReactNode }) {
  return <MemberNamesContext.Provider value={value}>{children}</MemberNamesContext.Provider>;
}

export function VerificationBadge({ status }: { status: string }) {
  if (status === "verified")
    return (
      <span className="inline-flex items-center gap-1 text-[12px] text-primary">
        <ShieldCheck className="size-3.5" /> Verified
      </span>
    );
  if (status === "flagged")
    return (
      <span className="inline-flex items-center gap-1 text-[12px] text-danger">
        <ShieldAlert className="size-3.5" /> Unconfirmed
      </span>
    );
  return null;
}

const str = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v : typeof v === "number" ? String(v) : null);
const num = (v: unknown): number | null => (typeof v === "number" && isFinite(v) ? v : null);
const safeUrl = (u?: string) => (u && /^https?:\/\//i.test(u) ? u : null);
const host = (u: string) => u.replace(/^https?:\/\/(www\.)?/, "").split("/")[0];

const VOTES: { choice: VoteChoice; label: string }[] = [
  { choice: "yes", label: "Yes" },
  { choice: "no", label: "No" },
  { choice: "wait", label: "Wait" },
];

function joinNames(list: string[]) {
  if (list.length <= 1) return list[0] ?? "";
  return `${list.slice(0, -1).join(", ")} and ${list.at(-1)}`;
}

export function VotingControls({ alertId, votes, onChange }: { alertId: number; votes: VoteSummary; onChange: (v: VoteSummary) => void }) {
  const [voting, setVoting] = useState<VoteChoice | null>(null);
  const { names, meId } = useContext(MemberNamesContext);

  async function vote(choice: VoteChoice) {
    setVoting(choice);
    try {
      const summary = await api.alerts.vote(alertId, choice);
      onChange({ ...votes, ...summary, my_vote: summary.my_vote ?? choice });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Vote failed");
    } finally {
      setVoting(null);
    }
  }

  const byChoice: Record<string, string[]> = {};
  for (const [uid, c] of Object.entries(votes.user_votes ?? {})) {
    const name = String(meId) === uid ? "You" : names.get(uid);
    if (name) (byChoice[c] ??= []).push(name);
  }
  const summary = VOTES.filter((v) => byChoice[v.choice]?.length)
    .map((v) => `${joinNames(byChoice[v.choice])} voted ${v.label}`)
    .join(" · ");

  return (
    <div className="space-y-2">
      <div className="inline-flex w-full rounded-full bg-muted p-1 sm:w-auto" role="group" aria-label="Should we act on this?">
        {VOTES.map(({ choice, label }) => {
          const mine = votes.my_vote === choice;
          return (
            <button
              key={choice}
              type="button"
              onClick={() => vote(choice)}
              disabled={voting !== null}
              aria-pressed={mine}
              className={cn(
                "flex h-8 flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-full px-4 text-[13px] font-medium transition-all disabled:cursor-wait sm:flex-none",
                mine ? "bg-surface text-foreground shadow-[0_1px_2px_rgb(24_24_27/0.08),0_0_0_1px_rgb(24_24_27/0.04)]" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {mine && <Check className="size-3.5 text-primary" />}
              {label}
              <span className="tabular-nums text-subtle">{votes[choice]}</span>
            </button>
          );
        })}
      </div>
      <p className="text-[12.5px] text-muted-foreground">{summary || `${votes.total_votes} of ${votes.total_members || "?"} voted`}</p>
    </div>
  );
}

interface CardProps {
  alert: Alert;
  watch?: Watch | null;
  compact?: boolean;
  className?: string;
  /** Hide "Details" when already on the detail page. */
  detailLink?: boolean;
}

interface Body {
  subtitle?: string | null;
  value?: string | null;
  delta?: React.ReactNode;
  target?: string | null;
  note?: React.ReactNode;
}

function ChangeText({ value, previous }: { value: number | null; previous?: string | null }) {
  if (value === null && !previous) return null;
  return (
    <span className="text-[13px] text-muted-foreground">
      {previous && <span className="line-through decoration-subtle">{previous}</span>}
      {previous && value !== null && " · "}
      {value !== null && (
        <span className={value < 0 ? "text-primary" : "text-warning"}>
          {value < 0 ? "↓" : "↑"} {Math.abs(value).toFixed(1)}%
        </span>
      )}
    </span>
  );
}

function AlertShell({ alert: initial, watch, compact, className, detailLink = true, kind, body }: CardProps & { kind: string; body: (a: Alert) => Body }) {
  const [alert, setAlert] = useState(initial);
  const [confirmBook, setConfirmBook] = useState(false);
  const [booking, setBooking] = useState(false);
  const [booked, setBooked] = useState<string | null>(watch?.status === "completed" ? "Booked" : null);
  const category = (str(alert.payload?.watch_type) ?? watch?.watch_type) as WatchType | undefined;
  const canBook = category === "flight" && !booked;
  const source = alert.sources.find((s) => safeUrl(s.url));
  const flightBookingSource = alert.sources.find(
    (s) => s.url && /^https:\/\/(?:www\.)?google\.com\/travel\/flights\b/i.test(s.url),
  );
  const b = body(alert);

  async function markBooked() {
    setBooking(true);
    try {
      const res = await api.alerts.complete(alert.id);
      setBooked(res.booked_by ? `Booked by ${res.booked_by}` : "Booked");
      toast.success("Marked as booked. Nazar stopped watching this fare.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not mark as booked");
    } finally {
      setBooking(false);
      setConfirmBook(false);
    }
  }

  async function share() {
    const text = alertShareText(alert);
    if (navigator.share) {
      try {
        await navigator.share({ title: alert.title, text });
        return;
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
      }
    }
    window.open(whatsappUrl(text), "_blank", "noopener,noreferrer");
  }

  return (
    <article className={cn("animate-card-in w-full max-w-[520px] rounded-[16px] border border-border bg-surface", alert.verification_status === "flagged" && "border-danger/25", className)}>
      <div className="space-y-4 p-5">
        <header className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
          <NazarAvatar className="size-6" />
          <span className="font-medium text-foreground">Nazar</span>
          <span aria-hidden>·</span>
          <span>{kind}</span>
          <span aria-hidden>·</span>
          <time dateTime={alert.created_at} title={dateTime(alert.created_at)}>
            {relativeTime(alert.created_at)}
          </time>
          <span className="ml-auto">
            <VerificationBadge status={alert.verification_status} />
          </span>
        </header>

        <div>
          <h3 className="text-[16px] font-semibold leading-snug">{alert.title}</h3>
          {b.subtitle && <p className="mt-0.5 text-[13.5px] text-muted-foreground">{b.subtitle}</p>}
        </div>

        {(b.value || b.delta) && (
          <div>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              {b.value && <span className="text-[28px] font-semibold leading-none tracking-[-0.03em] tabular-nums">{b.value}</span>}
              {b.delta}
            </div>
            {b.target && <p className="mt-1.5 text-[12.5px] text-muted-foreground">Target: {b.target}</p>}
          </div>
        )}
        {b.note}

        {alert.explanation && !compact && <p className="text-[14px] leading-relaxed text-foreground/80">{alert.explanation}</p>}

        {source && !compact && (
          <a href={safeUrl(source.url)!} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[13px] text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
            {source.title || host(source.url!)} <ArrowUpRight className="size-3.5" />
          </a>
        )}

        {alert.votes && <VotingControls alertId={alert.id} votes={alert.votes} onChange={(v) => setAlert((a) => ({ ...a, votes: v }))} />}
      </div>

      <footer className="flex items-center gap-1 border-t border-border px-3 py-2">
        {detailLink && (
          <Button variant="ghost" size="sm" asChild>
            <a href={`/alerts/${alert.id}`}>Details</a>
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={share}>
          Share
        </Button>
        {category === "flight" && safeUrl(flightBookingSource?.url) && (
          <Button size="sm" variant="secondary" asChild>
            <a href={safeUrl(flightBookingSource?.url)!} target="_blank" rel="noopener noreferrer">
              Book flight <ArrowUpRight aria-hidden />
            </a>
          </Button>
        )}
        <div className="ml-auto">
          {booked ? (
            <span className="inline-flex items-center gap-1 px-2 text-[13px] text-primary">
              <Check className="size-3.5" /> {booked}
            </span>
          ) : canBook && confirmBook ? (
            <div className="flex items-center gap-1">
              <Button size="sm" variant="ghost" onClick={() => setConfirmBook(false)} disabled={booking}>
                Cancel
              </Button>
              <Button size="sm" onClick={markBooked} loading={booking}>
                Confirm booked
              </Button>
            </div>
          ) : canBook ? (
            <Button size="sm" variant="secondary" onClick={() => setConfirmBook(true)}>
              Mark as booked
            </Button>
          ) : null}
        </div>
      </footer>
    </article>
  );
}

export function FlightAlertCard(props: CardProps) {
  const rule = props.watch?.rule_json.watch_type === "flight" ? props.watch.rule_json : null;
  return (
    <AlertShell
      {...props}
      kind="Flight"
      body={(a) => {
        const p = a.payload ?? {};
        const route = str(p.route) ?? (rule ? `${rule.origin} → ${rule.destination}` : null);
        return {
          subtitle: [route, str(p.travel_date), str(p.airline)].filter(Boolean).join(" · ") || null,
          value: a.observed_value,
          delta: <ChangeText value={num(p.change_percent)} previous={str(p.previous_value)} />,
          target: str(p.target) ?? (rule ? targetCondition(rule) : null),
        };
      }}
    />
  );
}

export function StockAlertCard(props: CardProps) {
  const rule = props.watch?.rule_json.watch_type === "stock" ? props.watch.rule_json : null;
  return (
    <AlertShell
      {...props}
      kind="Stock"
      body={(a) => {
        const p = a.payload ?? {};
        const symbol = str(p.symbol) ?? rule?.symbol;
        const exchange = str(p.exchange) ?? rule?.exchange;
        return {
          subtitle: symbol ? [symbol, exchange].filter(Boolean).join(" · ") : null,
          value: a.observed_value,
          delta: <ChangeText value={num(p.change_percent)} previous={str(p.previous_value)} />,
          target: str(p.target) ?? (rule ? targetCondition(rule) : null),
        };
      }}
    />
  );
}

export function JobAlertCard(props: CardProps) {
  const rule = props.watch?.rule_json.watch_type === "job_notification" ? props.watch.rule_json : null;
  return (
    <AlertShell
      {...props}
      kind="Job notice"
      body={(a) => {
        const p = a.payload ?? {};
        const domain = str(p.domain) ?? (safeUrl(a.sources[0]?.url) ? host(a.sources[0].url!) : null);
        const flagged = a.verification_status === "flagged";
        return {
          subtitle: [str(p.organization) ?? rule?.organization, str(p.notice_title)].filter(Boolean).join(" · ") || null,
          note:
            a.verification_status === "verified" || flagged ? (
              <p className={cn("text-[13px]", flagged ? "text-danger" : "text-muted-foreground")}>
                {flagged ? "Not found on an official domain. Verify before acting." : `Published on ${domain ?? "an official domain"}.`}
              </p>
            ) : null,
        };
      }}
    />
  );
}

export function TopicAlertCard(props: CardProps) {
  const rule = props.watch?.rule_json.watch_type === "topic" ? props.watch.rule_json : null;
  const priceWatch = rule ? rule.mode !== "new_results" : typeof props.alert.payload?.target === "string";
  return (
    <AlertShell
      {...props}
      kind={priceWatch ? "Price" : ({ news: "News", jobs: "Openings", web: "Update", shopping: "Price" } as const)[rule?.source ?? "web"]}
      body={(a) => {
        const p = a.payload ?? {};
        return priceWatch
          ? { subtitle: str(p.query) ?? rule?.query ?? null, value: a.observed_value, target: str(p.target) ?? (rule ? targetCondition(rule) : null) }
          : { subtitle: `Watching “${str(p.query) ?? rule?.query ?? ""}”` };
      }}
    />
  );
}

/** Picks the right card for the alert's category. */
export function AlertCard(props: CardProps) {
  const type = (str(props.alert.payload?.watch_type) ?? props.watch?.watch_type) as WatchType | undefined;
  if (type === "stock") return <StockAlertCard {...props} />;
  if (type === "job_notification") return <JobAlertCard {...props} />;
  if (type === "flight") return <FlightAlertCard {...props} />;
  if (type === "topic") return <TopicAlertCard {...props} />;
  return <AlertShell {...props} kind={WATCH_TYPE_LABEL[props.watch?.watch_type as WatchType] ?? "Alert"} body={(a) => ({ value: a.observed_value })} />;
}
