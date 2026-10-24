# Frontend

RepoViva's web app: React + Vite + TypeScript (decision 017). It calls Core API over REST with the session cookie, and Voice Service over a WebSocket for the live interview (decision 022).

## Pages

| Route | Page |
|---|---|
| `/` | Landing page with **Sign in with GitHub** |
| `/repositories` | Your repositories with status (ready, preparing, import failed), **Start interview** and **Retry**. Refreshes while one is preparing |
| `/repositories/new` | Connect a repository; accepts `owner/repo`, GitHub URLs and deep links |
| `/repositories/:id` | Indexing progress, then **Start interview** or a failure reason with **Retry** |
| `/repositories/:id/interview` | Setup: what to expect, a mic check with level meter, a speaker test, or typing mode |
| `/interviews/:id/live` | The live interview room (no sidebar) |
| `/interviews` | Reports: every interview taken, with **View report** once ended |
| `/interviews/:id/report` | Scores, strengths, answers to revisit, and key points linking to the exact lines on GitHub |

Signed-in pages share a sidebar (connect, repositories, reports, account menu with theme switch and sign out); on narrow screens it becomes a top bar. Light and dark themes follow the system until you pick one.

### The live interview

- The session token is sent as the first WebSocket message, never in the URL or browser storage (decision 035).
- Each question is shown as text and played as it streams in; it can be replayed or skipped. Progress shows "Question N of M".
- **Tap to answer, tap to send.** Mic audio is resampled to PCM16 16 kHz in the browser and sent in 100 ms chunks; recording stops on its own at 175 s.
- "What we heard" follows each answer. **Type instead** works for any turn or the whole interview.
- **End interview** still counts as completed; closing the tab ends it as interrupted, with a partial report.

## Layout

```
src/
  app/          router, signed-in layout (sidebar, account menu)
  api/          fetch wrapper and Core API types
  features/     auth · repositories · interview (setup, audio, live) · report
  components/   shared UI (Button, Card, ProgressBar, ScoreBar, …)
  hooks/        useResource, usePolling, useTheme
  styles/       tokens.css (palette, type, spacing), global.css
tests/          Vitest + Testing Library
```

Features use each other only through their `index.ts` (enforced by ESLint), and components use only the variables in `styles/tokens.css`.

## Run locally

Needs Node 20+ and Core API on port 8000; for interviews also Repository Service (8001) and Voice Service (8002).

```bash
npm install
npm run dev     # http://localhost:5173
```

Open it on **`localhost`**, not `127.0.0.1`: the session cookie is set by the OAuth callback on `localhost:8000` and only reaches `localhost`.

Vite proxies `/v1` to Core API and `/v1/ws` to Voice Service, so there is one origin and no CORS. Override the targets with `VITE_CORE_API_URL` and `VITE_VOICE_SERVICE_URL` in `.env`. In production Caddy does the same routing (decision 063).

## Checks

```bash
npm run lint && npm test
npm run build   # type check + production build
```
