// Mirrors backend/app/schemas/*.py. Keep in sync with the FastAPI response models.

export type ISODate = string;

export interface User {
  id: number;
  name: string;
  email: string;
  nexconn_user_id?: string | null;
  /** Nexconn user token issued by the backend (needed for NCEngine.connect). */
  nexconn_token?: string | null;
  created_at: ISODate;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Room {
  id: number;
  name: string;
  description?: string | null;
  invite_code: string;
  created_by: number;
  nexconn_conversation_id?: string | null;
  created_at: ISODate;
  member_count: number;
  my_role?: string | null;
  /** Optional member preview; rendered only when the backend includes it. */
  members?: Member[];
}

export interface Member {
  id: number;
  user_id: number;
  name: string;
  email: string;
  role: string;
  joined_at: ISODate;
  /** Presence, when the backend (or Nexconn) provides it. */
  online?: boolean;
  nexconn_user_id?: string | null;
}

export type RoomDetail = Room;

export interface Invite {
  room_id: number;
  invite_code: string;
  invite_url: string;
  whatsapp_url: string;
  message: string;
}

export interface ChatMessage {
  id: number;
  room_id: number;
  sender_id: number | null;
  sender_name?: string | null;
  message_text: string;
  message_type: string;
  provider_message_id?: string | null;
  created_at: ISODate;
}

export interface MessageWithBot {
  message: ChatMessage;
  bot_reply?: Record<string, unknown> | null;
}

export type WatchType = "flight" | "stock" | "job_notification" | "topic";
export type WatchStatus = "active" | "paused" | "completed" | "deleted" | "failed";

export interface FlightRule {
  watch_type: "flight";
  origin: string;
  destination: string;
  travel_date: string;
  return_date?: string | null;
  condition: "below" | "above";
  target_price: number;
  currency: string;
  travel_class?: string | null;
  passengers: number;
}

export interface StockRule {
  watch_type: "stock";
  symbol: string;
  exchange?: "NSE" | "BSE" | null;
  condition: "absolute_change_greater_than" | "price_below" | "price_above";
  threshold_percent?: number | null;
  target_price?: number | null;
  direction: "up" | "down" | "either";
}

export interface JobRule {
  watch_type: "job_notification";
  keywords: string[];
  organization?: string | null;
  domains: string[];
}

/** Anything else: a product price (Google Shopping) or new results for a search. */
export interface TopicRule {
  watch_type: "topic";
  query: string;
  source: "web" | "news" | "shopping" | "jobs";
  mode: "new_results" | "price_below" | "price_above";
  target_price?: number | null;
  currency: string;
}

export type WatchRule = FlightRule | StockRule | JobRule | TopicRule;

export interface Observation {
  id?: number;
  observed_value: number | null;
  observed_data?: Record<string, unknown>;
  checked_at: ISODate;
}

export interface Watch {
  id: number;
  room_id: number;
  created_by: number;
  watch_type: WatchType;
  rule_json: WatchRule;
  status: WatchStatus;
  check_interval: number;
  last_checked_at?: ISODate | null;
  next_check_at?: ISODate | null;
  last_triggered_at?: ISODate | null;
  last_alert_at?: ISODate | null;
  booked_by_id?: number | null;
  completed_at?: ISODate | null;
  created_at: ISODate;
  /** Optional extras; rendered only when the backend returns them. */
  latest_value?: number | string | null;
  history?: Observation[];
}

export interface ParseResult {
  understood: boolean;
  watch_type?: WatchType | null;
  rule?: WatchRule | null;
  missing_fields: string[];
  follow_up_question?: string | null;
  parser: string;
}

export type VoteChoice = "yes" | "no" | "wait";

export interface VoteSummary {
  alert_id: number;
  yes: number;
  no: number;
  wait: number;
  total_votes: number;
  total_members: number;
  my_vote?: VoteChoice | null;
  user_votes?: Record<string, string>;
}

export interface AlertSource {
  title?: string;
  url?: string;
  domain?: string;
  [key: string]: unknown;
}

export type VerificationStatus = "verified" | "flagged" | "unverified" | "not_applicable" | string;

export interface Alert {
  id: number;
  room_id: number;
  watch_id: number;
  title: string;
  observed_value?: string | null;
  explanation?: string | null;
  sources: AlertSource[];
  verification_status: VerificationStatus;
  event_key: string;
  created_at: ISODate;
  payload?: Record<string, unknown> | null;
  votes?: VoteSummary | null;
}

export interface CompleteResponse {
  alert_id: number;
  watch_id: number;
  watch_status: string;
  booked_by: string;
  message: string;
}
