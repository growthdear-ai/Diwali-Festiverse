import type { Watch, WatchRule, WatchType } from "./types";

/** Backend datetimes are naive UTC; treat strings without an offset as UTC. */
export function toDate(value?: string | null): Date | null {
  if (!value) return null;
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);
  return isNaN(d.getTime()) ? null : d;
}

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export function relativeTime(value?: string | null): string {
  const d = toDate(value);
  if (!d) return "—";
  const diff = (d.getTime() - Date.now()) / 1000;
  const abs = Math.abs(diff);
  if (abs < 45) return diff < 0 ? "just now" : "in a moment";
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  return rtf.format(Math.round(diff / 86400), "day");
}

export function dateTime(value?: string | null): string {
  const d = toDate(value);
  return d ? d.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "—";
}

/** "4 Dec" (adds the year only when it isn't the current one). */
export function shortDate(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  if (isNaN(d.getTime())) return iso;
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", ...(sameYear ? {} : { year: "numeric" }) });
}

/** "1 member" / "3 members". */
export const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** Next-check label; an overdue check reads "Due now" rather than "2 minutes ago". */
export function nextCheckLabel(w: Pick<Watch, "status" | "next_check_at">): string {
  if (w.status !== "active") return "—";
  const d = toDate(w.next_check_at);
  if (!d) return "—";
  return d.getTime() <= Date.now() + 30_000 ? "Due now" : relativeTime(w.next_check_at);
}

export function money(value: number, currency = "INR") {
  try {
    return new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
  } catch {
    return `${currency} ${value}`;
  }
}

export const WATCH_TYPE_LABEL: Record<WatchType, string> = {
  flight: "Flight",
  stock: "Stock",
  job_notification: "Govt Job",
  topic: "Other",
};

export function watchTitle(rule: WatchRule): string {
  switch (rule.watch_type) {
    case "flight":
      return `${rule.origin} → ${rule.destination}`;
    case "stock":
      return rule.exchange ? `${rule.symbol} · ${rule.exchange}` : rule.symbol;
    case "job_notification":
      return rule.organization || rule.keywords.join(", ");
    case "topic":
      return rule.query;
  }
}

export function targetCondition(rule: WatchRule): string {
  switch (rule.watch_type) {
    case "flight":
      return `${rule.condition === "below" ? "Below" : "Above"} ${money(rule.target_price, rule.currency)} · ${shortDate(rule.travel_date)} · ${plural(rule.passengers, "traveller")}`;
    case "stock":
      if (rule.condition === "absolute_change_greater_than") {
        const dir = rule.direction === "up" ? "up" : rule.direction === "down" ? "down" : "up or down";
        return `Moves ${dir} more than ${rule.threshold_percent}%`;
      }
      return `Price ${rule.condition === "price_below" ? "below" : "above"} ${money(rule.target_price ?? 0)}`;
    case "job_notification":
      return `“${rule.keywords.join(", ")}” on ${rule.domains[0] ?? "official sites"}${rule.domains.length > 1 ? ` +${rule.domains.length - 1}` : ""}`;
    case "topic":
      if (rule.mode !== "new_results") return `Price ${rule.mode === "price_below" ? "below" : "above"} ${money(rule.target_price ?? 0, rule.currency)} · Google Shopping`;
      return `New ${{ news: "news", jobs: "openings", web: "web results", shopping: "listings" }[rule.source]} as they appear`;
  }
}

/** Latest observed value: explicit field, else last history point. Never invented. */
export function latestValue(w: Watch): string | null {
  const raw = w.latest_value ?? w.history?.filter((h) => h.observed_value != null).at(-1)?.observed_value;
  if (raw == null || raw === "") return null;
  if (typeof raw === "string") return raw;
  if (w.rule_json.watch_type === "flight") return money(raw, w.rule_json.currency);
  if (w.rule_json.watch_type === "topic" && w.rule_json.mode !== "new_results") return money(raw, w.rule_json.currency);
  if (w.rule_json.watch_type === "stock") return `₹${raw.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
  return String(raw);
}
