"use client";

import { ArrowUp } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { NazarAvatar } from "@/components/common";
import { Button } from "@/components/ui/button";
import { toDate } from "@/lib/format";
import type { Member } from "@/lib/types";
import { cn } from "@/lib/utils";

const PALETTE = ["bg-[#e0f2fe] text-[#075985]", "bg-[#fce7f3] text-[#9d174d]", "bg-[#ede9fe] text-[#5b21b6]", "bg-[#fef3c7] text-[#92400e]", "bg-[#dcfce7] text-[#166534]", "bg-[#ffe4e6] text-[#9f1239]"];

export function initials(name: string) {
  return name
    .split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export function UserAvatar({ name, id, online, className }: { name: string; id: number | string; online?: boolean; className?: string }) {
  const tone = PALETTE[Math.abs(Number(String(id).replace(/\D/g, "")) || name.length) % PALETTE.length];
  return (
    <span className={cn("relative inline-grid size-8 shrink-0 place-items-center rounded-full text-[11px] font-semibold ring-2 ring-surface", tone, className)}>
      {initials(name)}
      {online !== undefined && (
        <span className={cn("absolute -bottom-px -right-px size-2.5 rounded-full ring-2 ring-surface", online ? "bg-[#22c55e]" : "bg-[#cbd5e1]")} aria-label={online ? "online" : "offline"} />
      )}
    </span>
  );
}

export function AvatarStack({ members, max = 4, size = "size-7" }: { members: Member[]; max?: number; size?: string }) {
  return (
    <span className="flex -space-x-2">
      {members.slice(0, max).map((m) => (
        <UserAvatar key={m.id} id={m.user_id} name={m.name} className={cn(size, "text-[10px]")} />
      ))}
      {members.length > max && <span className={cn("grid place-items-center rounded-full bg-muted text-[10px] font-medium text-muted-foreground ring-2 ring-surface", size)}>+{members.length - max}</span>}
    </span>
  );
}

export function DateSeparator({ date }: { date: Date }) {
  const today = new Date();
  const y = new Date(today);
  y.setDate(today.getDate() - 1);
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  const label = same(date, today) ? "Today" : same(date, y) ? "Yesterday" : date.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
  return (
    <div className="flex items-center gap-3 py-2" role="separator">
      <span className="h-px flex-1 bg-border" />
      <span className="rounded-full border border-border bg-surface px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">{label}</span>
      <span className="h-px flex-1 bg-border" />
    </div>
  );
}

export const clock = (iso: string) => toDate(iso)?.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }) ?? "";

function Highlight({ text, query, mine }: { text: string; query?: string; mine: boolean }) {
  const parts = text.split(/(@\w+)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("@")) return <span key={i} className={cn("font-semibold", mine ? "text-white" : "text-primary")}>{part}</span>;
        if (!query) return part;
        const idx = part.toLowerCase().indexOf(query.toLowerCase());
        if (idx < 0) return part;
        return (
          <span key={i}>
            {part.slice(0, idx)}
            <mark className="rounded-sm bg-[#fde68a] px-0.5 text-foreground">{part.slice(idx, idx + query.length)}</mark>
            {part.slice(idx + query.length)}
          </span>
        );
      })}
    </>
  );
}

/** A human message bubble. `grouped` hides avatar/name for consecutive messages from one sender. */
export function ChatMessage({ text, name, senderId, mine, time, pending, grouped, query }: { text: string; name: string; senderId: number | string; mine: boolean; time: string; pending?: boolean; grouped?: boolean; query?: string }) {
  return (
    <div className={cn("group flex gap-2.5", mine ? "flex-row-reverse" : "flex-row", grouped ? "mt-0.5" : "mt-3")}>
      <div className="w-8 shrink-0">{!mine && !grouped && <UserAvatar id={senderId} name={name} />}</div>
      <div className={cn("flex max-w-[78%] flex-col sm:max-w-[68%]", mine ? "items-end" : "items-start")}>
        {!mine && !grouped && <p className="mb-1 px-1 text-[12px] font-semibold text-foreground">{name}</p>}
        <div
          className={cn(
            "whitespace-pre-wrap break-words px-3.5 py-2 text-[14px] leading-relaxed shadow-[0_1px_1px_rgb(15_23_42/0.04)]",
            mine ? "rounded-[18px] rounded-br-[6px] bg-primary text-white" : "rounded-[18px] rounded-bl-[6px] bg-muted",
            pending && "opacity-60",
          )}
        >
          <Highlight text={text} query={query} mine={mine} />
        </div>
        <p className="mt-1 px-1 text-[10.5px] text-subtle opacity-0 transition-opacity group-hover:opacity-100">{pending ? "Sending…" : time}</p>
      </div>
    </div>
  );
}

export interface MentionTarget {
  id: string;
  name: string;
  bot: boolean;
}

/** Composer with @mention autocomplete (↑/↓/Enter/Tab), Shift+Enter for newline. */
export function MessageComposer({ onSend, sending, mentionables }: { onSend: (text: string) => Promise<boolean>; sending: boolean; mentionables: MentionTarget[] }) {
  const [text, setText] = useState("");
  const [index, setIndex] = useState(0);
  const ref = useRef<HTMLTextAreaElement>(null);
  const query = text.match(/(?:^|\s)@(\w*)$/)?.[1];
  const suggestions = useMemo(() => (query === undefined ? [] : mentionables.filter((s) => s.name.toLowerCase().startsWith(query.toLowerCase())).slice(0, 6)), [query, mentionables]);
  const active = suggestions.length ? index % suggestions.length : 0;

  function insert(name: string) {
    setText((t) => t.replace(/@(\w*)$/, `@${name.split(" ")[0]} `));
    setIndex(0);
    ref.current?.focus();
  }

  async function submit() {
    const body = text.trim();
    if (!body || sending) return;
    setText("");
    if (!(await onSend(body))) setText(body);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (suggestions.length) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        setIndex((i) => (i + (e.key === "ArrowDown" ? 1 : -1) + suggestions.length) % suggestions.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        insert(suggestions[active].name);
        return;
      }
      if (e.key === "Escape") return setText((t) => `${t} `);
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="relative bg-surface px-3 pb-[max(14px,env(safe-area-inset-bottom))] pt-2 sm:px-6">
      {suggestions.length > 0 && (
        <ul role="listbox" aria-label="Mention" className="animate-card-in absolute bottom-full left-3 mb-2 w-64 overflow-hidden rounded-[12px] border border-border bg-surface p-1 shadow-[var(--shadow-lg)] sm:left-5">
          {suggestions.map((s, i) => (
            <li key={s.id} role="option" aria-selected={i === active}>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  insert(s.name);
                }}
                className={cn("flex w-full cursor-pointer items-center gap-2.5 rounded-[8px] px-2.5 py-2 text-left text-[13px]", i === active ? "bg-muted" : "hover:bg-muted")}
              >
                {s.bot ? <NazarAvatar className="size-6" /> : <UserAvatar id={s.id} name={s.name} className="size-6 text-[9px] ring-0" />}
                <span className="font-medium">{s.name}</span>
                {s.bot && <span className="ml-auto text-[11.5px] text-subtle">Assistant</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="mx-auto flex max-w-3xl items-end gap-1 rounded-[22px] border border-border-strong bg-surface py-1 pl-3 pr-1 transition-colors focus-within:border-foreground/25">
        <textarea
          ref={ref}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          maxLength={4000}
          placeholder="Message, or type @Nazar to set up a watch"
          aria-label="Message"
          className="max-h-36 min-h-9 flex-1 resize-none bg-transparent px-1 py-2 text-[14px] text-foreground outline-none placeholder:text-subtle focus:outline-none focus-visible:outline-none"
          style={{ fieldSizing: "content" } as React.CSSProperties}
        />
        <Button size="icon" onClick={submit} disabled={!text.trim()} loading={sending} aria-label="Send" className="size-8 rounded-full">
          {!sending && <ArrowUp />}
        </Button>
      </div>
    </div>
  );
}
