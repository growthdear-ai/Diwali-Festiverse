import { env } from "./env";
import type {
  Alert,
  ChatMessage,
  CompleteResponse,
  Invite,
  MessageWithBot,
  ParseResult,
  Room,
  RoomDetail,
  TokenResponse,
  User,
  VoteChoice,
  VoteSummary,
  Watch,
  WatchRule,
  WatchType,
} from "./types";

const TOKEN_KEY = "nazar.token";
export const UNAUTHORIZED_EVENT = "nazar:unauthorized";

export const tokenStore = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string) {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {}
  },
  clear() {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {}
  },
};

/** True when a JWT's `exp` claim is in the past. Non-JWT tokens are treated as valid. */
export function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return typeof payload.exp === "number" && payload.exp * 1000 <= Date.now();
  } catch {
    return false;
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** FastAPI returns `detail` as a string or as a list of validation errors. */
function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { msg?: string; loc?: unknown[] }) => {
        const field = Array.isArray(d.loc) ? d.loc.filter((p) => p !== "body").join(".") : "";
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  return fallback;
}

type Method = "GET" | "POST" | "PATCH" | "DELETE";

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const token = tokenStore.get();
  let res: Response;
  try {
    res = await fetch(`${env.apiUrl}/api/v1${path}`, {
      method,
      headers: {
        Accept: "application/json",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Cannot reach the Nazar server. Check your connection and try again.");
  }

  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);

  if (res.status === 401 && token) {
    tokenStore.clear();
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  if (!res.ok) throw new ApiError(res.status, errorMessage(data, `Request failed (${res.status})`));
  return data as T;
}

/** List endpoints may return a bare array or a paginated `{ items }` envelope. */
function asList<T>(data: T[] | { items?: T[] } | null | undefined): T[] {
  if (Array.isArray(data)) return data;
  return data?.items ?? [];
}

function qs(params: Record<string, string | number | undefined | null>) {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return entries.length ? `?${new URLSearchParams(entries.map(([k, v]) => [k, String(v)]))}` : "";
}

export const api = {
  auth: {
    register: (data: { name: string; email: string; password: string }) =>
      request<TokenResponse>("POST", "/auth/register", data),
    login: (data: { email: string; password: string }) => request<TokenResponse>("POST", "/auth/login", data),
    me: () => request<User>("GET", "/auth/me"),
  },
  rooms: {
    list: async () => asList(await request<Room[]>("GET", "/rooms")),
    get: (id: number) => request<RoomDetail>("GET", `/rooms/${id}`),
    create: (data: { name: string; description?: string }) => request<Room>("POST", "/rooms", data),
    invite: (id: number) => request<Invite>("POST", `/rooms/${id}/invite`),
    join: (code: string) => request<Room>("POST", `/rooms/join/${encodeURIComponent(code)}`),
  },
  messages: {
    list: async (roomId: number) => asList(await request<ChatMessage[]>("GET", `/rooms/${roomId}/messages`)),
    send: (roomId: number, text: string) =>
      request<MessageWithBot>("POST", `/rooms/${roomId}/messages`, { message_text: text, message_type: "text" }),
  },
  watches: {
    parse: (text: string, roomId?: number) => request<ParseResult>("POST", "/watches/parse", { text, room_id: roomId }),
    create: (data: { room_id: number; watch_type: WatchType; rule: WatchRule; check_interval?: number }) =>
      request<Watch>("POST", "/watches", data),
    list: async (params: { room_id?: number; watch_type?: WatchType } = {}) =>
      asList(await request<Watch[]>("GET", `/watches${qs(params)}`)),
    get: (id: number) => request<Watch>("GET", `/watches/${id}`),
    update: (id: number, data: { rule?: WatchRule; check_interval?: number }) =>
      request<Watch>("PATCH", `/watches/${id}`, data),
    pause: (id: number) => request<Watch>("POST", `/watches/${id}/pause`),
    resume: (id: number) => request<Watch>("POST", `/watches/${id}/resume`),
    remove: (id: number) => request<void>("DELETE", `/watches/${id}`),
  },
  alerts: {
    list: async (params: { room_id?: number; watch_id?: number } = {}) =>
      asList(await request<Alert[]>("GET", `/alerts${qs(params)}`)),
    get: (id: number) => request<Alert>("GET", `/alerts/${id}`),
    vote: (id: number, choice: VoteChoice) => request<VoteSummary>("POST", `/alerts/${id}/vote`, { choice }),
    complete: (id: number) => request<CompleteResponse>("POST", `/alerts/${id}/complete`, { action: "booked" }),
  },
};
