"use client";

import { ArrowLeft, Sparkles } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { NazarAvatar, WatchTypeIcon } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Field, NativeSelect, Textarea } from "@/components/ui/field";
import { api } from "@/lib/api";
import { WATCH_TYPE_LABEL } from "@/lib/format";
import type { Room, Watch, WatchRule, WatchType } from "@/lib/types";
import { cn } from "@/lib/utils";
import { cleanRule, emptyRule, RuleEditor, validateRule } from "./rule-editor";

const INTERVALS = [15, 30, 60, 120, 360, 720, 1440];
const intervalLabel = (m: number) => (m < 60 ? `${m} min` : m < 1440 ? `${m / 60} h` : "Daily");

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rooms: Room[];
  /** Pre-selected room (e.g. from the chat). */
  roomId?: number;
  /** When set, the dialog edits this watch instead of creating one. */
  watch?: Watch;
  onSaved: (watch: Watch) => void;
}

export function WatchDialog({ open, onOpenChange, ...rest }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">{open && <WatchForm {...rest} onDone={() => onOpenChange(false)} />}</DialogContent>
    </Dialog>
  );
}

function WatchForm({ rooms, roomId, watch, onSaved, onDone }: Omit<Props, "open" | "onOpenChange"> & { onDone: () => void }) {
  const editing = Boolean(watch);
  const [step, setStep] = useState<"describe" | "confirm">(editing ? "confirm" : "describe");
  const [text, setText] = useState("");
  const [room, setRoom] = useState<number | "">(watch?.room_id ?? roomId ?? rooms[0]?.id ?? "");
  const [rule, setRule] = useState<WatchRule>(watch?.rule_json ?? emptyRule("flight"));
  const [interval, setIntervalMin] = useState(watch?.check_interval ?? 30);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [followUp, setFollowUp] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function parse() {
    if (text.trim().length < 3) return setFormError("Describe what Nazar should watch.");
    if (!room) return setFormError("Choose a room first.");
    setBusy(true);
    setFormError(null);
    try {
      const res = await api.watches.parse(text.trim(), Number(room));
      if (res.rule) setRule({ ...emptyRule((res.watch_type ?? res.rule.watch_type) as WatchType), ...res.rule } as WatchRule);
      else if (res.watch_type) setRule(emptyRule(res.watch_type));
      setFollowUp(res.understood ? null : res.follow_up_question || `Nazar needs: ${res.missing_fields.join(", ")}`);
      setStep("confirm");
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Could not understand that");
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    const errs = validateRule(rule);
    setErrors(errs);
    if (Object.keys(errs).length) return;
    if (!room) return setFormError("Choose a room.");
    setBusy(true);
    setFormError(null);
    try {
      const clean = cleanRule(rule);
      const saved = watch
        ? await api.watches.update(watch.id, { rule: clean, check_interval: interval })
        : await api.watches.create({ room_id: Number(room), watch_type: rule.watch_type, rule: clean, check_interval: interval });
      toast.success(editing ? "Watch updated" : "Nazar is now watching. It will post in the room when something changes.");
      onSaved(saved);
      onDone();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Could not save the watch");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <DialogTitle>{editing ? "Edit watch" : "New watch"}</DialogTitle>
        <DialogDescription>
          {step === "describe" ? "Tell Nazar what to keep an eye on, in plain words." : "Check the details. Nazar only alerts on exactly this rule."}
        </DialogDescription>
      </div>

      {step === "describe" ? (
        <>
          <Field label="Room" htmlFor="room">
            <NativeSelect id="room" value={room} onChange={(e) => setRoom(Number(e.target.value))} disabled={!rooms.length}>
              {!rooms.length && <option value="">Create a room first</option>}
              {rooms.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="What should Nazar watch?" htmlFor="nl">
            <Textarea
              id="nl"
              autoFocus
              rows={3}
              value={text}
              maxLength={2000}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && (e.metaKey || e.ctrlKey) && parse()}
              placeholder="Delhi to Goa flights for 4 people under ₹4,500 around 20 Dec"
            />
          </Field>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex gap-1.5">
              {(["flight", "stock", "job_notification", "topic"] as WatchType[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => {
                    setRule(emptyRule(t));
                    setFollowUp(null);
                    setStep("confirm");
                  }}
                  className="cursor-pointer rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-border-strong hover:text-foreground"
                >
                  Fill in {WATCH_TYPE_LABEL[t].toLowerCase()} manually
                </button>
              ))}
            </div>
            <Button onClick={parse} loading={busy} disabled={!rooms.length}>
              <Sparkles /> Understand
            </Button>
          </div>
        </>
      ) : (
        <>
          {followUp && (
            <div className="flex gap-3 rounded-[12px] border border-warning/25 bg-warning/5 p-3">
              <NazarAvatar className="size-7" />
              <p className="text-[13px] leading-relaxed text-foreground">{followUp}</p>
            </div>
          )}
          {!editing && (
            <div className="flex gap-1.5">
              {(["flight", "stock", "job_notification", "topic"] as WatchType[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => rule.watch_type !== t && setRule(emptyRule(t))}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 rounded-[10px] border px-2.5 py-1.5 text-[13px] transition-colors",
                    rule.watch_type === t ? "border-primary/40 bg-primary/5 text-foreground" : "border-border text-muted-foreground hover:text-foreground",
                  )}
                >
                  <WatchTypeIcon type={t} className="size-6 [&_svg]:size-3.5" /> {WATCH_TYPE_LABEL[t]}
                </button>
              ))}
            </div>
          )}
          <RuleEditor key={rule.watch_type} rule={rule} onChange={setRule} errors={errors} />
          <Field label="Check every" htmlFor="interval">
            <NativeSelect id="interval" value={interval} onChange={(e) => setIntervalMin(Number(e.target.value))}>
              {INTERVALS.map((m) => (
                <option key={m} value={m}>
                  {intervalLabel(m)}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <div className="flex items-center justify-between gap-2">
            {!editing ? (
              <Button variant="ghost" onClick={() => setStep("describe")} disabled={busy}>
                <ArrowLeft /> Back
              </Button>
            ) : (
              <span />
            )}
            <Button onClick={save} loading={busy}>
              {editing ? "Save changes" : "Start watching"}
            </Button>
          </div>
        </>
      )}
      {formError && (
        <p className="rounded-[10px] border border-danger/25 bg-danger/5 px-3 py-2 text-[13px] text-danger" role="alert">
          {formError}
        </p>
      )}
    </div>
  );
}
