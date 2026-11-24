import { appUrl } from "./env";
import type { Alert } from "./types";

// Link-based sharing via WhatsApp's public click-to-chat URL (no Business API).
export function whatsappUrl(text: string) {
  return `https://wa.me/?text=${encodeURIComponent(text)}`;
}

export function roomInviteText(roomName: string, inviteUrl: string) {
  return `Join our "${roomName}" room on Nazar Rakho. @Nazar keeps an eye on flights, stocks and govt jobs for us.\n\n${inviteUrl}`;
}

export function alertShareText(alert: Alert) {
  const lines = [`👁 Nazar alert: ${alert.title}`];
  if (alert.observed_value) lines.push(`Now: ${alert.observed_value}`);
  if (alert.explanation) lines.push("", alert.explanation.slice(0, 280));
  const src = alert.sources.find((s) => s.url)?.url;
  if (src) lines.push("", `Source: ${src}`);
  lines.push("", `Open in Nazar Rakho: ${appUrl(`/chat/${alert.room_id}`)}`);
  return lines.join("\n");
}
