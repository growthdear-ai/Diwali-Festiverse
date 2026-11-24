# Nazar Rakho — Backend

An AI-powered search and monitoring agent that lives inside family and friends group
chats. One-time questions return current, cited **SerpApi** results with optional
**You.com** research summaries. Explicit watch requests become validated rules checked
on a schedule, with alerts posted into **Nexconn** group conversations for **YES / NO /
WAIT** votes.

Built for the Beyond 9TO5 Buildathon. This repository contains the FastAPI backend;
`../frontend` is the Next.js frontend. The repository root `README.md` has the full
end-to-end setup and flow, including the two-room seed command.

**Current verification:** `46 passed` with `python -m pytest -q`, plus live smoke checks
against the configured provider accounts on 21 Nov 2026: Google Flights, Google Finance,
Google Search/Extract, You.com Research and Finance Research, Nexconn token issuance
with group text + custom alert-card delivery, and ambiguous-message parsing through local
Ollama (`llama3.2:3b`). See [Live integration status](#live-integration-status).

---

## Contents

- [How it works](#how-it-works)
- [Quickstart](#quickstart)
- [Configuration](#configuration)
- [Natural-language parser](#natural-language-parser)
- [Provider integrations](#provider-integrations-verified-contracts)
- [Monitoring lifecycle](#monitoring-lifecycle)
- [Alerts and voting](#alerts-and-voting)
- [API routes](#api-routes)
- [Security](#security)
- [Tests](#tests)
- [Live integration status](#live-integration-status)
- [Limitations and next steps](#limitations-and-next-steps)

---

## How it works

```
Nexconn group chat (@Nazar)
        │  post-message webhook
        ▼
FastAPI webhook ──► one-time question ──► Ollama refines query ──► SerpApi + You.com
        │                                                         │ results + sources
        └── explicit watch ──► parser ──► validated Watch          └── room reply
                                             │
                          APScheduler checks │
                                             ▼
                                      SerpApi providers
                                             │
                            You.com explanation on alert
                                             ▼
                        Alert ──► Nexconn ──► votes / completion
```

---

## Quickstart

Requires Python 3.11+.

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate      # Windows (bash). Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env               # provider keys for SerpApi / You.com / Nexconn

# Parser LLM (default: local Ollama, no API key needed)
ollama serve
ollama pull llama3.2:3b

uvicorn app.main:app --reload --port 8000
```

- Interactive API docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/api/v1/health>
- SQLite database: `backend/nazar.db` (created on startup)

The scheduler starts with the API process (`SCHEDULER_ENABLED=true`), so monitoring
continues when users close their browsers.

Mention `@Nazar` for an immediate web or shopping search, such as
`@Nazar phones under 60000`. Use explicit terms such as `watch`, `track`, or `alert`
when you want an ongoing monitor instead. Searches include source links and a
preference question so a short reply (for example, `Samsung`) can narrow the results.

### Minimal flow with curl

```bash
# 1. Register (returns a JWT)
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"name":"Asha","email":"asha@example.com","password":"password123"}'

TOKEN="<access_token from the response>"
AUTH="Authorization: Bearer $TOKEN"

# 2. Create a room. Pass the Nexconn channel id created by the ChatUI when available.
curl -s -X POST http://localhost:8000/api/v1/rooms \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"name":"Family","nexconn_conversation_id":"<channel-id>"}'

# 3. Preview parsing, then create the watch
curl -s -X POST http://localhost:8000/api/v1/watches/parse \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"text":"@Nazar Bangalore se Patna 30 Nov 2027 flight 6000 se kam ho toh batao"}'

curl -s -X POST http://localhost:8000/api/v1/watches \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{
    "room_id": 1,
    "watch_type": "flight",
    "rule": {
      "origin": "BLR", "destination": "PAT",
      "travel_date": "2027-11-30", "condition": "below",
      "target_price": 6000, "currency": "INR"
    }
  }'

# 4. Run the watch immediately instead of waiting for the scheduler
curl -s -X POST http://localhost:8000/api/v1/internal/watches/1/check

# 5. Inspect alerts and vote
curl -s "http://localhost:8000/api/v1/alerts?room_id=1" -H "$AUTH"
curl -s -X POST http://localhost:8000/api/v1/alerts/1/vote \
  -H "$AUTH" -H 'Content-Type: application/json' -d '{"choice":"yes"}'
```

---

## Configuration

All secrets come from environment variables / `.env`; nothing is hardcoded.

| Variable | Purpose | Default |
|---|---|---|
| `APP_ENV` | `development` / `production` | `development` |
| `SECRET_KEY` | JWT signing key (change in production) | insecure dev value |
| `DATABASE_URL` | SQLAlchemy URL | `sqlite:///./nazar.db` |
| `SERPAPI_API_KEY` | Live flights / stocks / job notices | empty |
| `YOU_API_KEY` | Research + Finance Research | empty |
| `NEXCONN_APP_KEY` | Nexconn app key | empty |
| `NEXCONN_APP_SECRET` | Nexconn signing secret (server only) | empty |
| `NEXCONN_API_HOST` | Nexconn data-center base URL | `https://api.sg-light-api.com` |
| `NEXCONN_BOT_USER_ID` | Bot identity used as `fromUserId` | `nazar-bot` |
| `NEXCONN_BOT_NAME` | Display name | `Nazar` |
| `NEXCONN_WEBHOOK_SECRET` | Optional inbound webhook HMAC secret | empty |
| `NEXCONN_ALERT_MESSAGE_TYPE` | Custom alert card message type | `NZ:AlertCard` |
| `NEXCONN_SEARCH_MESSAGE_TYPE` | Custom live search result message type | `NZ:SearchCard` |
| `NEXCONN_AUTO_CREATE_GROUPS` | Let the backend create group channels | `false` |
| `LLM_PROVIDER` | `auto`, `ollama`, or `openai` | `auto` (Ollama when no OpenAI key) |
| `LLM_BASE_URL` | Ollama or OpenAI-compatible base URL | `http://localhost:11434` for Ollama |
| `LLM_MODEL` / `LLM_OLLAMA_MODEL` | Chat model; OpenAI names auto-remap for Ollama | `llama3.2:3b` |
| `LLM_API_KEY` | Required for OpenAI-compatible providers; optional for Ollama | empty |
| `FRONTEND_URL` | Invite, share and alert deep links | `http://localhost:3000` |
| `SCHEDULER_ENABLED` | Start APScheduler in-process | `true` |
| `WATCH_INTERVAL_MINUTES` | Default check interval | `30` |
| `MAX_ALERTS_PER_WATCH_PER_DAY` | Daily cap per watch | `1` |
| `MORNING_BRIEF_ENABLED` | Daily group brief | `true` |
| `MORNING_BRIEF_HOUR_UTC` | Brief hour (UTC) | `1` |
| `BRIEF_LANGUAGE` | `en` or `hi` | `en` |
| `RATE_LIMIT_PER_MINUTE` | Per-IP API limit | `120` |
| `INTERNAL_API_TOKEN` | `X-Internal-Token` for `/internal/*` | empty (open in dev) |

The parser is deterministic for common English/Hinglish/Hindi phrasings; Ollama is used
only for ambiguous messages. Local Ollama needs no API key. Set `LLM_PROVIDER=openai`
plus `LLM_API_KEY` for a hosted OpenAI-compatible model. If the LLM is unreachable, the
parser falls back to a follow-up question instead of inventing a rule.

---

## Natural-language parser

`app/services/parser_service.py`:

1. Normalizes text (Devanagari digits, whitespace, `@Nazar` mention).
2. Classifies the watch type (`flight`, `stock`, `job_notification`).
3. Extracts airports/cities, dates, prices, percentages and comparison direction.
4. Resolves dates against **today**: an explicit day/month that has passed rolls to
   next year (`4 Nov` on 21 Nov → next 4 Nov), while an explicit year is respected.
5. Validates with Pydantic (`app/schemas/watch.py`) before anything is saved.
6. If a required field is missing, returns `missing_fields` + a follow-up question.
7. Falls back to a local Ollama model (native `/api/chat`, JSON format) or an
   OpenAI-compatible endpoint only when deterministic extraction is incomplete or
   invalid. Deterministically extracted airports, dates, prices, symbols and keywords
   always override LLM output, LLM-only values must be evidenced in the message, and the
   final rule is validated with Pydantic again.

Examples (with today = 2026-11-21):

| Message | Result |
|---|---|
| `@Nazar Bangalore se Patna 4 Nov ka flight 6000 se kam ho toh batao.` | flight, `BLR`→`PAT`, `2027-11-04`, `below`, `6000`, `INR` |
| `@Nazar Bangalore se Patna 30 Nov flight 6000 se kam` | flight, `2026-11-30` |
| `@Nazar Tata Motors 5% gir jaye toh batao` | stock, `TATAMOTORS`, `absolute_change_greater_than`, `5%`, `down` |
| `@Nazar SSC CGL notification aaye toh batao` | job, keywords `["SSC CGL"]`, official SSC domains |
| `Patna flight ka price batao` | follow-up: origin, destination, target price required |

Rule shapes are enforced by `FlightRule`, `StockRule`, `JobRule`; unknown keys are
rejected (`extra="forbid"`), flight dates cannot be in the past, and stock conditions
require either `threshold_percent` or `target_price`.

---

## Provider integrations (verified contracts)

Documentation was checked before implementing (21 Nov 2026).

### SerpApi — primary monitoring engine

Central client: `app/integrations/serpapi_client.py` (httpx, 3 attempts with exponential
backoff, 429/5xx retry, 10-minute TTL cache for identical queries, `no_cache` never
forced). All responses are real provider payloads; nothing is fabricated.

- **Flights** — `engine=google_flights`, `departure_id`, `arrival_id`, `outbound_date`,
  `type=2` (one-way) or `type=1` with `return_date`, `currency`, `travel_class`,
  `adults`, `hl=en`, `gl=in`. The lowest `best_flights`/`other_flights` price is used;
  `price_insights.lowest_price` is only a fallback when no itinerary price is present.
  Source: <https://serpapi.com/google-flights-api>
- **Stocks** — `engine=google_finance`, `q=<SYMBOL>:NSE` then `:BSE` when the exchange
  is  not specified. The exchange identifier is accepted only when the live response
  returns a usable `summary`. Percentage movement comes from
  `summary.price_movement`; previous close comes from `knowledge_graph.key_stats` when
  Google provides it, otherwise it is derived arithmetically from the live day-change
  value (`price ± |movement.value|`) and flagged via `previous_close_source`. The
  comparison baseline is explicitly **previous close**.
  Source: <https://serpapi.com/google-finance-api>
- **Government jobs** — `engine=google` + `engine=google_news`, restricted with
  `site:` clauses to official domains (`ssc.gov.in`, `ibps.in`, `rrbcdg.gov.in`,
  `upsc.gov.in`, etc.). Search uses `tbs=qdr:y` and drops official home pages as well as
  results that do not contain the watch keywords, so years-old PDFs and generic pages do
  not create alerts. Google News is queried without `so` (SerpApi rejects `q` + `so`
  together). An official result is marked `verified` only when the SerpApi **Extract
  API** (`engine=extract`) returns page content matching the watch keywords; otherwise
  it is `unverified`, and mismatching content is `flagged`. Search presence alone never
  verifies a notice. PDF notices may not be extractable and therefore remain
  `unverified`. Sources:
  <https://serpapi.com/google-news-api>, <https://serpapi.com/extract-api>

### You.com — explanation and verification only

`app/integrations/you_client.py`, `X-API-Key` header:

- Research: `POST https://api.you.com/v1/research` with `input`, `research_effort`,
  optional `source_control.include_domains`. Used for flights (lite), job notice
  verification (lite, restricted to official domains) and general explanations.
- Finance Research: `POST https://api.you.com/v1/finance_research` with `input` and
  `research_effort` (`deep`; this API has no lite tier). Used only for stock triggers.
- SerpApi supplies numbers; You.com supplies context and citations. Returned
  `output.content` and `output.sources[*].url/title` are stored and shown.
- **Cost control:** You.com is called only after a threshold crossing or a new notice,
  never on every scheduler run. If it fails, the alert is still created with verified
  raw data and an explicit "research explanation unavailable" note.

Docs: <https://you.com/docs/guides/research>,
<https://you.com/docs/guides/finance-research>

### Nexconn — group messaging

`app/integrations/nexconn_client.py`, verified against <https://docs.nexconn.ai>:

- Every request: `App-Key`, `Nonce` (≤18 chars), `Timestamp` (ms), `Signature =
  SHA1(App Secret + Nonce + Timestamp)`, JSON body, optional `X-Request-ID`.
- Access token / user registration: `POST /v4/auth/access-token/issue`.
- Group message: `POST /v4/group-channel/message/send` with `fromUserId`,
  `toChannelIds`, `messageType`, `content` (serialized JSON string), `pushContent`,
  `shouldPersist`, `isEchoToSender`.
- Text: `RC:TxtMsg`. Alert cards: custom type `NZ:AlertCard` (override with
  `NEXCONN_ALERT_MESSAGE_TYPE`). **The ChatUI must register this custom message type**
  or the client cannot render the card.
- Live search results use custom type `NZ:SearchCard` (override with
  `NEXCONN_SEARCH_MESSAGE_TYPE`); the frontend's `NEXT_PUBLIC_NEXCONN_SEARCH_MESSAGE_TYPE`
  must match so result links and booking buttons render.
- Offline push is triggered through `pushContent` on every group message; this is how
  alerts reach members whose browsers are closed.
- Room ↔ conversation mapping: `rooms.nexconn_conversation_id`; user mapping:
  `users.nexconn_user_id`. Recommended flow is to create the group in the Nexconn
  ChatUI and pass its channel id when creating the Nazar room. Optional auto-creation
  (`NEXCONN_AUTO_CREATE_GROUPS=true`) calls `/v4/group-channel/create` with the
  documented `channelId`, `name` and `owner` fields (the API returns a code-only
  response, so Nazar generates and returns the channel id); it is off by default.
- Inbound callback: `POST /api/v1/webhooks/nexconn`. Payloads are parsed tolerantly
  (`data.message`, `messages[]`, `channelId`/`targetId`, string or object `content`),
  messages are idempotent by provider message id, and the bot ignores its own messages.
- Webhook signing: Nexconn's public docs do not publish a webhook signature algorithm,
  so the backend does **not** invent one. Set `NEXCONN_WEBHOOK_SECRET` to enforce an
  HMAC-SHA256 header (`X-Nexconn-Signature`, optionally `sha256=`-prefixed), or protect
  the endpoint with network controls / a gateway token.

---

## Monitoring lifecycle

`app/services/monitoring_service.py` + `app/workers/`:

1. APScheduler runs every `WATCH_INTERVAL_MINUTES` (default 30) with
   `max_instances=1` and coalescing; an in-process in-flight set also prevents
   concurrent duplicate checks.
2. Due, active watches are selected (batch limit, default 20).
3. The matching provider fetches a live observation.
4. The observation is normalized and saved to `watch_history`.
5. The condition is evaluated against the **previous** observation. An alert is only
   eligible on a *new crossing* (not while it remains true) or a *new unique notice*.
6. Duplicate suppression: unique `(watch_id, event_key)` and a daily cap
   (`MAX_ALERTS_PER_WATCH_PER_DAY`, default 1).
7. You.com runs only for a qualifying trigger.
8. The alert is saved, then delivered to the mapped Nexconn conversation as a custom
   card plus a vote prompt.
9. Provider failures are logged and rescheduled; one failing watch never stops the run.
10. Timestamps are stored as naive UTC and emitted with a `Z` suffix.

Flights: round-trip watches use the initial Google Flights response (outbound
itineraries). Fetching return legs would need a second `departure_token` request and is
not part of the MVP.

---

## Alerts and voting

Alert card payload (`build_alert_payload`):

```json
{
  "type": "flight_alert",
  "alert_id": 12,
  "room_id": 1,
  "watch_id": 3,
  "title": "Flight fare dropped: BLR → PAT (₹5,640)",
  "current_value": 5640,
  "target_value": 6000,
  "currency": "INR",
  "explanation": "Research-backed explanation with citations.",
  "sources": [{"url": "https://...", "title": "..."}],
  "verification_status": "not_applicable",
  "actions": ["yes", "no", "wait"],
  "share_url": "http://localhost:3000/alerts/12"
}
```

Stock alerts also include `disclaimer: "Information only, not financial advice."`;
job alerts include organization/keywords and `verification_status` of
`verified` / `unverified` / `flagged`.

Voting:

- One vote per member per alert; voting again **updates** the existing vote.
- Tallies return yes/no/wait, total votes, total members, per-user votes and `my_vote`.
- Chat shortcuts: `1/yes/haan`, `2/no/nahi`, `3/wait/ruk` (only applied to the most
  recent alert in that room, within 7 days).
- `BOOKED` (or `POST /alerts/{id}/complete`) marks the watch `completed`, records
  `booked_by_id` and `completed_at`, clears `next_check_at`, notifies the group and stops
  all future checks.
- WhatsApp sharing uses click-to-chat URLs only (`https://wa.me/?text=...`) for invites
  and alerts; the WhatsApp Business API is intentionally not integrated.

Morning brief (`app/workers/morning_brief.py`) summarises active watches, last-24h
changes, verified job notices, pending decisions and recent alerts in English or Hindi,
then posts it into each mapped Nexconn group.

---

## API routes

All routes are under `/api/v1` and require a Bearer JWT except register/login,
health, and the Nexconn webhook.

| Method | Path | Notes |
|---|---|---|
| POST | `/auth/register` | Returns JWT + user (409 on duplicate email) |
| POST | `/auth/login` | Returns JWT + user |
| GET | `/auth/me` | Current user |
| POST | `/rooms` | Create room, owner membership, optional conversation id |
| GET | `/rooms` | Rooms the caller belongs to |
| GET | `/rooms/{id}` | Room detail (member only) |
| POST | `/rooms/{id}/invite` | Invite code, invite URL, WhatsApp share URL |
| POST | `/rooms/join/{code}` | Join by invite code (idempotent) |
| GET | `/rooms/{id}/members` | Members (member only) |
| GET | `/rooms/{id}/messages` | Message history (member only) |
| POST | `/rooms/{id}/messages` | Store message; runs @Nazar bot if mentioned |
| POST | `/webhooks/nexconn` | Nexconn callback, idempotent by message id |
| POST | `/watches/parse` | Message → validated rule / follow-up |
| POST | `/watches` | Create watch (`room_id` in body or query) |
| GET | `/watches` | List watches; optional `room_id`, `status`, `watch_type` (account-wide without `room_id`) |
| GET | `/watches/{id}` | Watch detail (member only) |
| PATCH | `/watches/{id}` | Update rule and/or interval |
| POST | `/watches/{id}/pause` | Pause checks |
| POST | `/watches/{id}/resume` | Resume checks |
| DELETE | `/watches/{id}` | Delete watch and its history/alerts |
| GET | `/alerts` | Alerts with vote tallies; optional `room_id`, `watch_id` (account-wide without `room_id`) |
| GET | `/alerts/{id}` | Alert detail with payload |
| POST | `/alerts/{id}/vote` | `{"choice":"yes"\|"no"\|"wait"}` |
| GET | `/alerts/{id}/votes` | Vote tally |
| POST | `/alerts/{id}/complete` | Mark BOOKED, stop the watch (body optional) |
| GET | `/alerts/{id}/share` | Short summary + WhatsApp share URL |
| GET | `/health` | DB, provider configuration and scheduler status |
| GET | `/internal/workers/status` | Scheduler jobs + in-flight count |
| POST | `/internal/watches/{id}/check` | Force a check (manual/internal) |
| POST | `/internal/morning-brief` | Send the brief now |

`/internal/*` requires `X-Internal-Token` when `INTERNAL_API_TOKEN` is set, and is
refused in production without a token.

---

## Security

- PBKDF2-HMAC-SHA256 password hashing (260k iterations, per-password salt).
- JWT bearer auth with expiry; no secrets or hashes are ever returned.
- Room-level authorization on watches, messages, alerts, votes and members — access to
  another room returns 403/404, never data.
- Secure random invite codes (8 chars from a 32-char alphabet); invite URLs can be
  regenerated by creating a new room.
- Input validation everywhere via Pydantic (rule unions, dates, percentages, IATA codes).
- Webhook idempotency plus optional HMAC verification.
- Per-IP sliding-window rate limiting on auth, parsing and webhook routes, with a
  configurable global default.
- Provider timeouts, retries with backoff, and graceful degradation.
- CORS restricted to `FRONTEND_URL` (plus localhost in development).
- Production startup refuses a default or short `SECRET_KEY` and warns on unsafe
  deployment settings.
- SQLite runs in WAL mode with a busy timeout, and legacy demo columns are migrated away
  on startup.
- There is no runtime demo or mock data path: every observation comes from a live
  provider, and provider failures surface as `unavailable`/`error`, never fake values.

---

## Tests

```bash
cd backend
python -m pytest -q
# 46 passed
```

Coverage highlights (all provider calls mocked; no network):

- Hinglish/English rule parsing, date roll-over, missing-field follow-ups
- Flight lowest-fare normalization + below/above comparison
- Stock percentage movement, previous-close baseline, NSE→BSE resolution
- Job notice deduplication, official-domain filtering, page verification and
  `flagged`/`unverified` outcomes
- New-crossing detection, no repeat alerts while true, daily cap, job dedup
- Provider failure handling without crashing or alerting
- Ollama native `/api/chat` request shape, OpenAI-model remapping, hallucinated-value
  override by deterministic anchors, and graceful fallback when Ollama is down
- Production startup rejecting an insecure `SECRET_KEY`
- Vote creation, vote updates, tally and non-member rejection
- Room-level authorization for rooms, watches, alerts and deletes
- BOOKED completion stopping future checks
- Nexconn signature, signed headers, group alert-card payload, documented
  group-create body (`channelId`/`name`/`owner`) and webhook HMAC
- Nexconn webhook → watch creation, idempotent duplicate delivery
- Health endpoint never exposing keys

---

## Live integration status

Live smoke checks were run on 21 Nov 2026 with the keys loaded from `backend/.env`
(environment variables alone were not set).

| Integration | Live result |
|---|---|
| SerpApi Google Flights | ✓ BLR→PAT on 2026-12-21 returned ₹9,330 lowest fare (IndiGo) with a real `google.com/travel/flights` source URL |
| SerpApi Google Finance | ✓ ITC:NSE ₹299.10, −0.63%; Google omitted the previous-close stat, so ₹301.00 was derived from the live day-change and marked `google_finance_price_movement` |
| SerpApi Google Search/News + Extract | ✓ recent official SSC PDF found after `qdr:y` + relevance filtering; its page was not extractable, so it stayed `unverified` (no false `verified`) |
| You.com Research (lite) | ✓ 647-character cited answer with 7 sources |
| You.com Finance Research (deep) | ✓ 2,479-character cited answer with 6 sources, including `itcportal.com` |
| Nexconn signing + access token | ✓ `/v4/auth/access-token/issue` returned an access token for the smoke-test user |
| Nexconn group + text + card | ✓ group created, `RC:TxtMsg` sent, and the `NZ:AlertCard` custom payload accepted |
| Ollama parser (`llama3.2:3b`) | ✓ native `/api/chat` parsed an ambiguous Hinglish flight request; deterministic anchors corrected a hallucinated airport and year |
| APScheduler | ✓ starts/stops with the app lifespan; tests run with it disabled |

Live checks surfaced and fixed three real issues: deriving the stock baseline when
Google omits it, the `google_news` `q`+`so` rejection, and Nexconn group creation using
`owner`/`channelId` instead of `userId`. The Nexconn smoke test created the user
`nazar-smoke-test` and the group `Nazar Smoke Test`; delete them in the Nexconn console
if they are not wanted.

Automated tests mock provider responses so they run offline. The running application has
no demo or simulated-data path: it always calls the configured live provider, and a
missing key produces a clear `missing_key` health status and a safe `unavailable` watch
result. To re-validate live, create a watch and call
`POST /api/v1/internal/watches/{id}/check`, then inspect the returned `observed_value`
and the stored alert `sources`.

---

## Limitations and next steps

- APScheduler runs inside the API process; run a single worker instance or move the
  scheduler to a dedicated process before horizontal scaling.
- SQLite is used per the brief; switch to Postgres for concurrent production writes.
- The SerpApi cache and rate limiter are in-process; use Redis for multi-instance
  deployments.
- Nexconn's webhook signature scheme is not publicly documented; the optional HMAC check
  is a deployment-level safeguard, not an official protocol.
- The Web ChatUI must register the `NZ:AlertCard` custom message type (and ideally the
  vote action buttons) to render alert cards.
- Flights monitor outbound fares; return-leg tokens and passenger baggage filters are
  out of scope.
- WhatsApp is click-to-chat only by design; no Business API.
- The optional MCP server (`create_watch`, `list_watches`, `pause_watch`, `get_alerts`)
  was deliberately deferred so it could not delay the working MVP. It can wrap the
  existing services behind a thin stdio MCP transport without changing this core.

### Project layout

```
backend/
  app/
    main.py                 # FastAPI app, health, internal endpoints
    api/                    # auth, rooms, messages, watches, alerts, votes, webhooks
    core/                   # config, database, security
    models/                 # User, Room, RoomMember, Watch, WatchHistory, Alert, Vote, Message
    schemas/                # auth, room, watch rules, alert, vote
    services/               # parser, watch, monitoring, alert, voting, room, bot, auth
    integrations/           # serpapi, flight, stock, jobs, you, nexconn
    workers/                # scheduler, watch_worker, morning_brief
    utils/                  # normalization, deduplication, validators
  tests/                    # 45 tests
  requirements.txt
  .env.example
  README.md
```
