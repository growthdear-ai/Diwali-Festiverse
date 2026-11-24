// Only public, browser-safe values. The Nexconn App Key is a client credential
// (the official ChatUI quick start passes it to NCEngine.initialize in the browser);
// the App Secret stays on the backend.
export const env = {
  apiUrl: (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, ""),
  nexconnAppKey: process.env.NEXT_PUBLIC_NEXCONN_APP_KEY || "",
  nexconnBotUserId: process.env.NEXT_PUBLIC_NEXCONN_BOT_USER_ID || "nazar-bot",
  nexconnAlertMessageType: process.env.NEXT_PUBLIC_NEXCONN_ALERT_MESSAGE_TYPE || "NZ:AlertCard",
  nexconnSearchMessageType: process.env.NEXT_PUBLIC_NEXCONN_SEARCH_MESSAGE_TYPE || "NZ:SearchCard",
};

export function appUrl(path = "") {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return `${origin}${path}`;
}
