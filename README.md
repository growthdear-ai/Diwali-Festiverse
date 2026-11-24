# Nazar Rakho

Nazar Rakho is a group-chat search and monitoring agent. A member can ask `@Nazar` a
question for current web or shopping results, or explicitly ask it to watch flights,
stocks, prices, jobs, or news. Searches return cited results immediately; watches are
checked by the scheduler and create alerts only when a real change occurs.

The product runs with real provider data only. There is no in-browser demo mode, no
sample-data seed, and no runtime fallback to mock prices or notices. The optional seed
command creates two rooms with real watch rules; actual values still come from the
configured providers.

---

## 1. Architecture

```
Frontend (Next.js)
  login / rooms / chat / watches / alerts / voting
        │  JWT REST
        ▼
FastAPI backend
  auth ─ rooms ─ messages ─ watches ─ alerts ─ votes ─ webhooks
        │
        ├── deterministic parser + local Ollama fallback
        ├── APScheduler checks active watches
        ├── SerpApi: Google Flights / Google Finance / Google Search / Google News
        ├── You.com: Research / Finance Research for explanations
        ├── Nexconn: group messages and custom alert cards
        ├── Lyzr: Structured verification of watch results (verified/no_change/needs_review)
        ├── BAND: Scout→Verifier agent collaboration room (live WebSocket + REST)
        └── SQLite (WAL) or PostgreSQL through DATABASE_URL
```

### Watch Verification Flow (Lyzr + BAND)

When Lyzr and BAND are configured, threshold-based watch checks (flights, stocks, price-topic) follow an extended flow:

1. **Nazar's providers** gather the observation and source links as usual.
2. **Nazar Scout (BAND agent)** posts the candidate change with evidence to the BAND room.
3. **Nazar Verifier (BAND agent)** invokes the **Lyzr agent** for structured analysis.
4. **Lyzr** returns `verified`, `no_change`, or `needs_review` with explanation and cited source evidence.
5. **Verification validation**: Nazar backend validates the Lyzr response — requires source evidence for `verified`, treats missing evidence as `needs_review`.
6. **Verifier posts result** to BAND room with decision.
7. **Only `verified` changes** proceed to Nazar's existing alert persistence and delivery (Nexconn/room).
8. If `no_change` or `needs_review`: no alert is sent; uncertainty is recorded in the BAND room for human review.

Job and "new results" topic watches skip this flow and use the original path (You.com research + direct alert).

### What happens to one message

1. A user mentions `@Nazar` with a question, such as `phones under 60000`.
2. For a one-time question, local Ollama refines the search wording without supplying
   results. SerpApi fetches current listings or web results, and You.com adds a sourced
   research summary when available.
3. Nazar replies in the room with the results, source links, and a short question to
   narrow the results (for example, preferred phone brand or storage size).
4. A user can instead explicitly ask Nazar to watch or alert them, such as
   `@Nazar track SSC CGL notification`. The backend parses and validates a watch rule.
5. The scheduler checks due watches with SerpApi; a real change creates a source-backed,
   deduplicated alert, and You.com explains it when available.
6. Alerts are delivered to the room/Nexconn, where members can vote **YES / NO / WAIT**
   or mark a flight as booked. A daily morning brief summarizes the rooms.

---

## 2. Prerequisites

- Python 3.11+
- Node.js 20+ and npm
- Ollama (default local parser; no API key) or an OpenAI-compatible LLM
- SerpApi key for live search, shopping results, and watch checks
- You.com key for sourced research summaries and alert explanations (direct search results
  still appear if You.com is unavailable)
- Optional: Nexconn app key/secret and a public webhook URL
- Optional: Lyzr Enterprise API key and Agent ID (for structured watch verification)
- Optional: BAND agent credentials (Scout + Verifier agent IDs/keys, room ID) for live collaboration

---

## 3. Backend setup

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate       # Windows bash
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env                # then fill in provider keys
```

Required `.env` values for a full setup:

```dotenv
APP_ENV=development
SECRET_KEY=<long random string, 32+ chars>
DATABASE_URL=sqlite:///./nazar.db
FRONTEND_URL=http://localhost:3000

SERPAPI_API_KEY=...
YOU_API_KEY=...

# Default local parser (no key needed)
LLM_PROVIDER=ollama
LLM_BASE_URL=http://localhost:11434
LLM_OLLAMA_MODEL=llama3.2:3b

# Optional Nexconn integration
NEXCONN_APP_KEY=...
NEXCONN_APP_SECRET=...
NEXCONN_BOT_USER_ID=nazar-bot
NEXCONN_WEBHOOK_SECRET=...

# Optional Lyzr Enterprise (structured watch verification)
LYZR_ENABLED=false
LYZR_API_KEY=
LYZR_AGENT_ID=
LYZR_AGENT_URL=

# Optional BAND (Scout→Verifier agent collaboration room)
BAND_ENABLED=false
BAND_SCOUT_AGENT_ID=
BAND_SCOUT_API_KEY=
BAND_VERIFIER_AGENT_ID=
BAND_VERIFIER_API_KEY=
BAND_ROOM_ID=
BAND_API_HOST=https://api.band.ai
BAND_WS_HOST=wss://api.band.ai
```

Start Ollama:

```bash
ollama serve
ollama pull llama3.2:3b
```

Start the API:

```bash
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

Check it:

```bash
curl http://localhost:8000/api/v1/health
# OpenAPI: http://localhost:8000/docs
```

The health response reports database status, scheduler status, configured providers,
and the resolved LLM provider/model/base URL. It never returns provider secrets.

### BAND WebSocket Listener (optional, for live agent collaboration)

If `BAND_ENABLED=true` and credentials are configured, run the WebSocket listener
to receive live mentions and room messages in the BAND collaboration room:

```bash
cd backend
.venv/Scripts/python.exe -m workers.band_listener
```

This keeps a persistent WebSocket connection to BAND, enabling the Scout and Verifier
agents to receive @mentions and human replies in real time. The listener is optional;
the REST-based Scout→Verifier handoff works without it.

### Two starter rooms (optional, explicit)

This command creates or reuses a local account and seeds **two rooms** with real,
validated watch rules. It does not insert any sample prices, fares or notices.

```bash
cd backend
.venv/Scripts/python.exe -m scripts.seed_rooms
```

Defaults:

- Email: `munazir@nazar.local`
- Password: `nazar-local-2026` (only used when the account is created)
- Rooms: **Family Travel** (BLR → PAT below ₹6,000) and **Money & Jobs**
  (ITC 3% move, SSC CGL official notice watch)

Use your own account and password:

```bash
.venv/Scripts/python.exe -m scripts.seed_rooms \
  --email you@example.com --password "your-password" --name "Your Name"
```

The command is idempotent: running it again does not duplicate rooms or watches.
Charts and latest values stay empty until the scheduler makes real provider checks.

---

## 4. Frontend setup

```bash
cd frontend
cp .env.example .env.local
# edit .env.local
npm install
npm run dev
```

Frontend environment:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_NEXCONN_APP_KEY=              # public app key; never the app secret
NEXT_PUBLIC_NEXCONN_BOT_USER_ID=nazar-bot
NEXT_PUBLIC_NEXCONN_ALERT_MESSAGE_TYPE=NZ:AlertCard
NEXT_PUBLIC_NEXCONN_SEARCH_MESSAGE_TYPE=NZ:SearchCard
```

Open `http://localhost:3000`, register or log in, and use the seeded rooms or create
your own. The Nexconn app key is public client configuration; the Nexconn app secret
belongs only in `backend/.env`.

---

## 5. Complete user flow

1. **Register / log in** at `/register` or `/login`. The backend returns a JWT; the
   frontend stores it and calls `/auth/me` for the current user.
2. **Create a room** or use the two seeded rooms. Every room has an owner, members and
   an invite code. Share the invite link or WhatsApp link from the room page.
3. **Join a room** with a code or `/join/<code>` link. Room access is checked on every
   API call; a non-member cannot read or mutate room data.
4. **Chat with @Nazar** in `/chat/<roomId>`. If Nexconn is configured and the room has
   a Nexconn conversation id, the UI uses Nexconn ChatUI. Otherwise it falls back to the
   backend relay and all messages still go through the same parser.
5. **Ask for a watch** in natural language. The chat reply creates the watch and posts a
   bot confirmation. You can also create one from `/watches` using the form.
6. **See live checks** on `/watches`: latest value, sparkline, last/next check. The watch
   detail page shows the full price history and previous alerts from `watch_history`.
7. **Receive an alert** in `/alerts` and in the room chat when the rule crosses. Each
   alert contains the observed value, an explanation, sources, verification status and
   an alert-specific vote summary.
8. **Vote** YES / NO / WAIT. Votes are scoped to the room and update for everyone.
9. **Mark a flight as booked** from an alert. The watch becomes `completed` and the
   scheduler stops checking it.
10. **Morning brief** is sent by the scheduler to configured rooms with the previous
    day's activity. Internal endpoints can trigger a check or brief manually.

The dashboard lists watches and alerts across all rooms the signed-in user belongs to.
The backend's `GET /watches` and `GET /alerts` are account-wide when `room_id` is omitted.

---

## 6. API map

| Area | Endpoints |
| --- | --- |
| Auth | `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me` |
| Rooms | `GET/POST /api/v1/rooms`, `GET /api/v1/rooms/{id}`, `POST /api/v1/rooms/join/{code}`, `POST /api/v1/rooms/{id}/invite`, `GET /api/v1/rooms/{id}/members` |
| Messages | `GET/POST /api/v1/rooms/{id}/messages` |
| Watches | `POST /api/v1/watches/parse`, `GET/POST /api/v1/watches`, `GET/PATCH/DELETE /api/v1/watches/{id}`, `POST /api/v1/watches/{id}/pause`, `POST /api/v1/watches/{id}/resume` |
| Alerts | `GET /api/v1/alerts`, `GET /api/v1/alerts/{id}`, `POST /api/v1/alerts/{id}/vote`, `POST /api/v1/alerts/{id}/complete`, `GET /api/v1/alerts/{id}/share` |
| Votes | `GET /api/v1/alerts/{id}/votes` |
| Webhooks | `POST /api/v1/webhooks/nexconn` (idempotent by provider message id) |
| Operations | `GET /api/v1/health`, protected internal check/brief/worker-status routes |

`GET /watches` and `GET /alerts` accept `room_id`; `GET /alerts` also accepts
`watch_id`. `GET /watches` accepts `status` and `watch_type`. Watch responses include
`latest_value` and up to 60 real history points for the UI charts.

---

## 7. Verification

```bash
cd backend
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m compileall -q app scripts

cd ../frontend
npx tsc --noEmit
npm run lint
npm run build
```

The backend test suite is offline by design: provider HTTP calls are mocked so tests do
not spend credits. Live rooms never fall back to simulated data; missing keys mean that
provider's checks fail or are unavailable, and the health endpoint says so.

---

## 8. Production checklist

- Set `APP_ENV=production` and a random `SECRET_KEY` of 32+ characters. Startup rejects
  the default/insecure key.
- Use PostgreSQL for multi-instance deployments. SQLite WAL is supported for a
  single-instance deployment and is migrated forward on startup.
- Run one scheduler process (or move checks to a standalone worker) when deploying more
  than one API instance; APScheduler is in-process today.
- Set `INTERNAL_API_TOKEN` and protect the internal worker endpoints.
- Put the API and frontend behind HTTPS; set `FRONTEND_URL` to the public origin.
- Set `NEXCONN_WEBHOOK_SECRET` and expose the webhook over HTTPS.
- Add provider keys and verify them from `/api/v1/health` and one forced check.
- Back up the database. Alembic is not included; startup migrations cover the small
  schema additions in this repository.

## 9. Honest limitations

- No fake fallback data: if SerpApi/You.com/Nexconn is down or unconfigured, the UI shows
  an error or an alert without a research explanation rather than invented content.
- The frontend uses Nexconn ChatUI when configured, otherwise a backend message relay.
  Calls, file attachments and presence are not implemented; the UI hides or labels them.
- Government-job verification depends on the official domains in the rule and the
  provider results. It does not guarantee that a notice is currently open.
- Stock and flight data are informational, not financial or booking advice.
