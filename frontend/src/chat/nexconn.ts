"use client";

// The ONLY module that talks to the Nexconn SDKs. Everything else goes through
// `connectNexconn` / `openGroup` / `disconnectNexconn`. APIs used here are taken from
// @nexconn/chat@26.5.x and @nexconn/chatui@26.5.x type definitions.
import type { NCChatUIApplication } from "@nexconn/chatui";
import { env } from "@/lib/env";
import { defineNazarMessageElement } from "./nazar-message-element";

export interface NexconnDirectory {
  currentUser: { userId: string; name: string };
  /** Nexconn group id → display data, resolved from backend rooms. */
  group(groupId: string): { name: string; memberCount: number } | null;
  /** Nexconn group id → members (Nexconn user ids + names), resolved from backend room members. */
  members(groupId: string): Promise<{ userId: string; name: string }[]>;
}

let app: NCChatUIApplication | null = null;
let connecting: Promise<NCChatUIApplication> | null = null;
let directory: NexconnDirectory | null = null;

export const nexconnAvailable = () => Boolean(env.nexconnAppKey);

export function connectNexconn(token: string, dir: NexconnDirectory): Promise<NCChatUIApplication> {
  directory = dir;
  if (app) return Promise.resolve(app);
  if (connecting) return connecting;

  connecting = (async () => {
    const { NCEngine, LogLevel } = await import("@nexconn/chat");
    const { NCChatUIApplication, BubbleLayout, ChatUICommand } = await import("@nexconn/chatui");

    NCEngine.initialize({ appKey: env.nexconnAppKey, logLevel: LogLevel.WARN });

    const bot = env.nexconnBotUserId;
    const ui = NCChatUIApplication.initialize({
      language: "en_US",
      hooks: {
        reqUserProfiles: async (userIds) => {
          const known = new Map<string, string>([[bot, "Nazar"]]);
          if (directory) known.set(directory.currentUser.userId, directory.currentUser.name);
          return userIds.map((userId) => ({ userId, name: known.get(userId) ?? userId }));
        },
        reqGroupProfiles: async (groupIds) =>
          groupIds.map((groupId) => {
            const g = directory?.group(groupId);
            return { groupId, name: g?.name ?? "Room", memberCount: g?.memberCount ?? 0 };
          }),
        reqSystemProfiles: async () => [],
        // Includes @Nazar so the built-in mention panel offers the bot.
        reqGroupMembers: async (groupId) => {
          const list = (await directory?.members(groupId)) ?? [];
          const members = list.map((m) => ({ userId: m.userId, nickname: m.name }));
          if (!members.some((m) => m.userId === bot)) members.unshift({ userId: bot, nickname: "Nazar" });
          return members;
        },
      },
    });
    if (!ui) throw new Error("Nexconn ChatUI failed to initialize.");

    ui.setChannelBarSwitch(false);
    ui.setCommandSwitch(ChatUICommand.MENTION_ALL, true);
    ui.setMessageBubbleConfig({
      layout: BubbleLayout.LEFT_RIGHT,
      redius: 14,
      backgroundColorForMyself: 0x2dd4a0,
      textColorForMyself: 0x04261b,
      showOthersNameInGroupChannel: true,
    });
    ui.setPushConfigHook((message) => ({
      pushTitle: "Nazar Rakho",
      pushContent: typeof message.content?.text === "string" ? message.content.text.slice(0, 120) : "New message",
      pushData: JSON.stringify({ channelId: message.channelIdentifier.channelId }),
    }));
    // Backend-sent Nazar cards render as React inside ChatUI.
    const nazarMessageElement = defineNazarMessageElement();
    ui.registerCustomMessages([
      {
        messageType: env.nexconnAlertMessageType,
        isPersisted: true,
        isCounted: true,
        digest: () => "[Nazar alert]",
        component: { tagName: "nazar-message", elementClass: nazarMessageElement, disableDefaultBubblePadding: true },
      },
      {
        messageType: env.nexconnSearchMessageType,
        isPersisted: true,
        isCounted: true,
        digest: () => "[Nazar search results]",
        component: { tagName: "nazar-message", elementClass: nazarMessageElement, disableDefaultBubblePadding: true },
      },
    ]);
    ui.ready();

    const result = await NCEngine.connect({ token });
    if (!result.isOk) {
      ui.destroy();
      throw new Error(`Nexconn connection failed (code ${result.code}${result.msg ? `: ${result.msg}` : ""}).`);
    }
    app = ui;
    return ui;
  })();

  connecting.catch(() => {
    connecting = null;
  });
  return connecting;
}

export async function openGroup(groupId: string) {
  if (!app) throw new Error("Nexconn is not connected.");
  const { GroupChannelIdentifier } = await import("@nexconn/chat");
  const res = await app.openChannel(new GroupChannelIdentifier(groupId), true);
  if (!res.isOk) throw new Error(`Could not open the Nexconn conversation (code ${res.code}).`);
}

export async function disconnectNexconn() {
  if (!app && !connecting) return;
  const { NCEngine } = await import("@nexconn/chat");
  await NCEngine.disconnect().catch(() => {});
  app?.destroy();
  app = null;
  connecting = null;
}
