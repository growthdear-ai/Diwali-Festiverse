# Nazar Rakho — Frontend

Next.js app for the Nazar Rakho group-monitoring product. It talks to the FastAPI
backend at `NEXT_PUBLIC_API_URL` and has no in-browser demo or sample-data mode.

## Run

```bash
cp .env.example .env.local
npm install
npm run dev
```

`.env.local`:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_NEXCONN_APP_KEY=              # public client key, optional
NEXT_PUBLIC_NEXCONN_BOT_USER_ID=nazar-bot
NEXT_PUBLIC_NEXCONN_ALERT_MESSAGE_TYPE=NZ:AlertCard
NEXT_PUBLIC_NEXCONN_SEARCH_MESSAGE_TYPE=NZ:SearchCard
```

The backend must be running for login, rooms, watches, alerts and voting. The Nexconn
App Secret must never be placed in this app; only the backend uses it.

## Flow

1. Register or log in.
2. Open a room (or create one) and mention `@Nazar` with a flight, stock or job request.
3. The backend parses and validates the request, then creates a watch.
4. The scheduler checks live providers and records real observations.
5. Alerts appear in the room and in **Alerts**; members vote YES / NO / WAIT.
6. Flight alerts can be marked booked, which completes the watch.

If Nexconn is configured for a room, chat uses Nexconn ChatUI; otherwise the app uses
the backend message relay. See the repository root `README.md` for the complete setup,
two-room seed command, API map and production checklist.

## Checks

```bash
npx tsc --noEmit
npm run lint
npm run build
```
