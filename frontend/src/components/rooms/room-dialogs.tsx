"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/field";
import { api } from "@/lib/api";
import type { Room } from "@/lib/types";

export function CreateRoomModal({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (o: boolean) => void; onCreated: (r: Room) => void }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const n = name.trim();
    if (n.length < 2 || n.length > 160) return setError("Room name must be 2–160 characters.");
    setBusy(true);
    setError(null);
    try {
      const room = await api.rooms.create({ name: n, ...(description.trim() ? { description: description.trim() } : {}) });
      onCreated(room);
      onOpenChange(false);
      setName("");
      setDescription("");
      toast.success(`“${room.name}” is ready. Invite your people.`);
      router.push(`/rooms?room=${room.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create room");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Create a room</DialogTitle>
        <DialogDescription>A shared group chat for family or friends, with @Nazar already in it.</DialogDescription>
        <form onSubmit={submit} className="mt-5 space-y-4" noValidate>
          <Field label="Room name" htmlFor="room-name" error={error}>
            <Input id="room-name" autoFocus value={name} maxLength={160} onChange={(e) => setName(e.target.value)} placeholder="Sharma Family" aria-invalid={Boolean(error)} />
          </Field>
          <Field label="Description (optional)" htmlFor="room-desc">
            <Textarea id="room-desc" rows={2} maxLength={300} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Diwali trip and Papa's stocks" />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={busy}>
              Create room
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Accepts a raw code or a full invite link (…/join/CODE). */
export function extractInviteCode(input: string) {
  const s = input.trim();
  return (s.match(/\/join\/([^/?#\s]+)/)?.[1] ?? s).trim();
}

export function JoinRoomDialog({ open, onOpenChange, onJoined }: { open: boolean; onOpenChange: (o: boolean) => void; onJoined: (r: Room) => void }) {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const c = extractInviteCode(code);
    if (c.length < 4) return setError("Enter the invite code or paste the invite link.");
    setBusy(true);
    setError(null);
    try {
      const room = await api.rooms.join(c);
      onJoined(room);
      onOpenChange(false);
      setCode("");
      toast.success(`Joined “${room.name}”`);
      router.push(`/chat/${room.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not join room");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Join a room</DialogTitle>
        <DialogDescription>Paste the invite link or code someone shared with you.</DialogDescription>
        <form onSubmit={submit} className="mt-5 space-y-4" noValidate>
          <Field label="Invite code or link" htmlFor="invite-code" error={error}>
            <Input id="invite-code" autoFocus value={code} onChange={(e) => setCode(e.target.value)} placeholder="e.g. 7KQ2-MX9P" aria-invalid={Boolean(error)} autoComplete="off" />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={busy}>
              Join room
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
