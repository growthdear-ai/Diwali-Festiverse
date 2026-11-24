"use client";

import { Field, Input, NativeSelect } from "@/components/ui/field";
import type { FlightRule, JobRule, StockRule, TopicRule, WatchRule, WatchType } from "@/lib/types";

export function emptyRule(type: WatchType): WatchRule {
  if (type === "flight")
    return { watch_type: "flight", origin: "", destination: "", travel_date: "", condition: "below", target_price: 0, currency: "INR", passengers: 1 };
  if (type === "stock") return { watch_type: "stock", symbol: "", exchange: "NSE", condition: "absolute_change_greater_than", threshold_percent: 3, direction: "either" };
  if (type === "topic") return { watch_type: "topic", query: "", source: "web", mode: "new_results", currency: "INR" };
  return { watch_type: "job_notification", keywords: [], domains: ["upsc.gov.in", "ssc.nic.in"] };
}

/** Mirrors backend/app/schemas/watch.py validators so users see errors before submitting. */
export function validateRule(rule: WatchRule): Record<string, string> {
  const e: Record<string, string> = {};
  if (rule.watch_type === "flight") {
    if (!/^[A-Z]{3}$/.test(rule.origin)) e.origin = "3-letter airport code, e.g. DEL";
    if (!/^[A-Z]{3}$/.test(rule.destination)) e.destination = "3-letter airport code, e.g. BOM";
    if (rule.origin && rule.origin === rule.destination) e.destination = "Must differ from origin";
    const today = new Date().toISOString().slice(0, 10);
    if (!rule.travel_date) e.travel_date = "Pick a travel date";
    else if (rule.travel_date < today) e.travel_date = "Date can't be in the past";
    if (rule.return_date && rule.return_date < rule.travel_date) e.return_date = "Must be on or after travel date";
    if (!(rule.target_price > 0)) e.target_price = "Enter a price above 0";
    if (!(rule.passengers >= 1 && rule.passengers <= 9)) e.passengers = "1 to 9 passengers";
  } else if (rule.watch_type === "stock") {
    if (!/^[A-Z0-9][A-Z0-9&.-]{0,31}$/.test(rule.symbol)) e.symbol = "Letters, numbers, &, . or -";
    if (rule.condition === "absolute_change_greater_than" && !(rule.threshold_percent && rule.threshold_percent > 0 && rule.threshold_percent <= 100))
      e.threshold_percent = "Between 0 and 100";
    if (rule.condition !== "absolute_change_greater_than" && !(rule.target_price && rule.target_price > 0)) e.target_price = "Enter a price above 0";
  } else if (rule.watch_type === "topic") {
    if (rule.query.trim().length < 2) e.query = "Describe what to watch";
    if (rule.mode !== "new_results" && !(rule.target_price && rule.target_price > 0)) e.target_price = "Enter a price above 0";
  } else {
    if (!rule.keywords.length) e.keywords = "Add at least one keyword";
    if (!rule.domains.length) e.domains = "Add at least one official domain";
  }
  return e;
}

/** Strips empty optionals so the backend's `extra="forbid"` models accept the rule. */
export function cleanRule(rule: WatchRule): WatchRule {
  if (rule.watch_type === "flight") {
    const { return_date, travel_class, ...rest } = rule;
    return { ...rest, ...(return_date ? { return_date } : {}), ...(travel_class ? { travel_class } : {}) };
  }
  if (rule.watch_type === "stock") {
    const r: StockRule = { ...rule };
    if (r.condition === "absolute_change_greater_than") delete r.target_price;
    else delete r.threshold_percent;
    if (!r.exchange) delete r.exchange;
    return r;
  }
  if (rule.watch_type === "topic") {
    const r: TopicRule = { ...rule, query: rule.query.trim() };
    if (r.mode === "new_results") delete r.target_price;
    else r.source = "shopping"; // price watches always read Google Shopping
    return r;
  }
  const { organization, ...rest } = rule;
  return { ...rest, ...(organization ? { organization } : {}) };
}

const list = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

export function RuleEditor({ rule, onChange, errors }: { rule: WatchRule; onChange: (r: WatchRule) => void; errors: Record<string, string> }) {
  const err = (k: string) => errors[k];
  const inv = (k: string) => ({ "aria-invalid": Boolean(errors[k]), "aria-describedby": errors[k] ? `${k}-error` : undefined });

  if (rule.watch_type === "flight") {
    const set = (patch: Partial<FlightRule>) => onChange({ ...rule, ...patch });
    return (
      <div className="grid grid-cols-2 gap-3">
        <Field label="From" htmlFor="origin" error={err("origin")}>
          <Input id="origin" value={rule.origin} maxLength={3} placeholder="DEL" onChange={(e) => set({ origin: e.target.value.toUpperCase() })} {...inv("origin")} />
        </Field>
        <Field label="To" htmlFor="destination" error={err("destination")}>
          <Input id="destination" value={rule.destination} maxLength={3} placeholder="GOI" onChange={(e) => set({ destination: e.target.value.toUpperCase() })} {...inv("destination")} />
        </Field>
        <Field label="Travel date" htmlFor="travel_date" error={err("travel_date")}>
          <Input id="travel_date" type="date" value={rule.travel_date} onChange={(e) => set({ travel_date: e.target.value })} {...inv("travel_date")} />
        </Field>
        <Field label="Return (optional)" htmlFor="return_date" error={err("return_date")}>
          <Input id="return_date" type="date" value={rule.return_date ?? ""} onChange={(e) => set({ return_date: e.target.value || null })} {...inv("return_date")} />
        </Field>
        <Field label="Alert when fare is" htmlFor="condition">
          <NativeSelect id="condition" value={rule.condition} onChange={(e) => set({ condition: e.target.value as FlightRule["condition"] })}>
            <option value="below">Below</option>
            <option value="above">Above</option>
          </NativeSelect>
        </Field>
        <Field label={`Target price (${rule.currency})`} htmlFor="target_price" error={err("target_price")}>
          <Input id="target_price" type="number" min={1} value={rule.target_price || ""} onChange={(e) => set({ target_price: Number(e.target.value) })} {...inv("target_price")} />
        </Field>
        <Field label="Passengers" htmlFor="passengers" error={err("passengers")}>
          <Input id="passengers" type="number" min={1} max={9} value={rule.passengers} onChange={(e) => set({ passengers: Number(e.target.value) })} {...inv("passengers")} />
        </Field>
        <Field label="Class" htmlFor="travel_class">
          <NativeSelect id="travel_class" value={rule.travel_class ?? ""} onChange={(e) => set({ travel_class: e.target.value || null })}>
            <option value="">Any</option>
            <option value="economy">Economy</option>
            <option value="premium_economy">Premium economy</option>
            <option value="business">Business</option>
            <option value="first">First</option>
          </NativeSelect>
        </Field>
      </div>
    );
  }

  if (rule.watch_type === "stock") {
    const set = (patch: Partial<StockRule>) => onChange({ ...rule, ...patch });
    const pct = rule.condition === "absolute_change_greater_than";
    return (
      <div className="grid grid-cols-2 gap-3">
        <Field label="Symbol" htmlFor="symbol" error={err("symbol")}>
          <Input id="symbol" value={rule.symbol} placeholder="RELIANCE" onChange={(e) => set({ symbol: e.target.value.toUpperCase() })} {...inv("symbol")} />
        </Field>
        <Field label="Exchange" htmlFor="exchange">
          <NativeSelect id="exchange" value={rule.exchange ?? ""} onChange={(e) => set({ exchange: (e.target.value || null) as StockRule["exchange"] })}>
            <option value="NSE">NSE</option>
            <option value="BSE">BSE</option>
            <option value="">Any</option>
          </NativeSelect>
        </Field>
        <Field label="Condition" htmlFor="stock_condition" className="col-span-2">
          <NativeSelect id="stock_condition" value={rule.condition} onChange={(e) => set({ condition: e.target.value as StockRule["condition"] })}>
            <option value="absolute_change_greater_than">Moves more than X%</option>
            <option value="price_below">Price drops below</option>
            <option value="price_above">Price rises above</option>
          </NativeSelect>
        </Field>
        {pct ? (
          <>
            <Field label="Threshold (%)" htmlFor="threshold_percent" error={err("threshold_percent")}>
              <Input id="threshold_percent" type="number" step="0.1" min={0.1} max={100} value={rule.threshold_percent ?? ""} onChange={(e) => set({ threshold_percent: Number(e.target.value) })} {...inv("threshold_percent")} />
            </Field>
            <Field label="Direction" htmlFor="direction">
              <NativeSelect id="direction" value={rule.direction} onChange={(e) => set({ direction: e.target.value as StockRule["direction"] })}>
                <option value="either">Up or down</option>
                <option value="up">Up only</option>
                <option value="down">Down only</option>
              </NativeSelect>
            </Field>
          </>
        ) : (
          <Field label="Target price (₹)" htmlFor="stock_target" error={err("target_price")} className="col-span-2">
            <Input id="stock_target" type="number" min={0.01} step="0.01" value={rule.target_price ?? ""} onChange={(e) => set({ target_price: Number(e.target.value) })} {...inv("target_price")} />
          </Field>
        )}
      </div>
    );
  }

  if (rule.watch_type === "topic") {
    const set = (patch: Partial<TopicRule>) => onChange({ ...rule, ...patch });
    const price = rule.mode !== "new_results";
    return (
      <div className="grid grid-cols-2 gap-3">
        <Field label="What to watch" htmlFor="query" error={err("query")} className="col-span-2" hint="A product, company, topic or anything you can search for.">
          <Input id="query" value={rule.query} placeholder="iPhone 16, Infosys SDE jobs, Patna airport…" onChange={(e) => set({ query: e.target.value })} {...inv("query")} />
        </Field>
        <Field label="Alert me when" htmlFor="topic_mode" className={price ? "" : "col-span-2"}>
          <NativeSelect
            id="topic_mode"
            value={rule.mode}
            onChange={(e) => {
              const mode = e.target.value as TopicRule["mode"];
              set(mode === "new_results" ? { mode, source: rule.source === "shopping" ? "web" : rule.source } : { mode, source: "shopping" });
            }}
          >
            <option value="new_results">Something new appears</option>
            <option value="price_below">Price drops below</option>
            <option value="price_above">Price rises above</option>
          </NativeSelect>
        </Field>
        {price ? (
          <Field label="Target price (₹)" htmlFor="topic_target" error={err("target_price")}>
            <Input id="topic_target" type="number" min={1} value={rule.target_price ?? ""} onChange={(e) => set({ target_price: Number(e.target.value) })} {...inv("target_price")} />
          </Field>
        ) : (
          <Field label="Look in" htmlFor="topic_source" className="col-span-2">
            <NativeSelect id="topic_source" value={rule.source} onChange={(e) => set({ source: e.target.value as TopicRule["source"] })}>
              <option value="web">Web</option>
              <option value="news">News</option>
              <option value="jobs">Job openings</option>
            </NativeSelect>
          </Field>
        )}
      </div>
    );
  }

  const set = (patch: Partial<JobRule>) => onChange({ ...rule, ...patch });
  return (
    <div className="grid gap-3">
      <Field label="Keywords (comma separated)" htmlFor="keywords" error={err("keywords")}>
        <Input id="keywords" defaultValue={rule.keywords.join(", ")} placeholder="SSC CGL, notification" onChange={(e) => set({ keywords: list(e.target.value) })} {...inv("keywords")} />
      </Field>
      <Field label="Organization (optional)" htmlFor="organization">
        <Input id="organization" value={rule.organization ?? ""} placeholder="Staff Selection Commission" onChange={(e) => set({ organization: e.target.value || null })} />
      </Field>
      <Field label="Official domains only" htmlFor="domains" error={err("domains")} hint="Notices from other sites are flagged, never shown as verified.">
        <Input id="domains" defaultValue={rule.domains.join(", ")} onChange={(e) => set({ domains: list(e.target.value).map((d) => d.toLowerCase()) })} {...inv("domains")} />
      </Field>
    </div>
  );
}
