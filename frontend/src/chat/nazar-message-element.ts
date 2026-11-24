"use client";

import { createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { BotMessage, toBotPayload } from "@/components/nazar/bot-message";

/**
 * Web Component that Nexconn ChatUI mounts for our custom message type.
 * ChatUI assigns `.message` (a ChatUIMessageModel); we render the React BotMessage
 * into a shadow root that carries a copy of the app's stylesheets.
 */
export function defineNazarMessageElement(): CustomElementConstructor {
  return class NazarMessageElement extends HTMLElement {
    private root: Root | null = null;
    private _message: { content?: unknown; sentTime?: number } | null = null;

    set message(value: { content?: unknown; sentTime?: number } | null) {
      this._message = value;
      this.render();
    }

    get message() {
      return this._message;
    }

    connectedCallback() {
      if (!this.root) {
        const shadow = this.shadowRoot ?? this.attachShadow({ mode: "open" });
        // ChatUI renders inside shadow DOM, so global CSS doesn't reach us. Copy it in.
        document.querySelectorAll('link[rel="stylesheet"], style').forEach((n) => shadow.appendChild(n.cloneNode(true)));
        const mount = document.createElement("div");
        mount.style.cssText = "display:block;padding:2px 0;font-family:var(--font-geist-sans),system-ui,sans-serif;";
        shadow.appendChild(mount);
        this.root = createRoot(mount);
      }
      this.render();
    }

    disconnectedCallback() {
      const root = this.root;
      this.root = null;
      // Defer so React isn't unmounted mid-render of the ChatUI list.
      queueMicrotask(() => root?.unmount());
      this.shadowRoot?.replaceChildren();
    }

    private render() {
      if (!this.root || !this._message) return;
      const payload = toBotPayload(this._message.content);
      if (!payload.created_at && this._message.sentTime) payload.created_at = new Date(this._message.sentTime).toISOString();
      this.root.render(createElement(BotMessage, { payload }));
    }
  };
}
