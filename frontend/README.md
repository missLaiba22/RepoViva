# Frontend

RepoViva's web app: React + Vite + TypeScript (decision 017). It talks to Core API over REST with the session cookie, and will talk to Voice Service over a WebSocket for the live interview (decision 022).

## What's implemented

- **Landing page** (`/`): what RepoViva does in three steps, and **Sign in with GitHub**.
- **Home** (`/home`, signed in only):
  - Repositories with their indexing status. While any is indexing, the list refreshes every 3 s.
  - **Start interview** on repositories that are ready.
  - Recent interviews (completed, ended early, in progress), with **View report** once an interview has ended.
- **Connect a repository** (`/repositories/new`):
  - One link field. It accepts what people paste: `owner/repo`, `github.com/owner/repo`, `.git` URLs and links deeper into a repository. It shows the URL it will send.
  - A repository you've already connected (Core API's 409) opens that repository instead of showing an error.
- **Repository page** (`/repositories/:id`):
  - While indexing: a progress bar, refreshed every 2 s.
  - When ready: **Start interview**.
  - When failed: the reason, and a way forward.
- **Interview setup** (`/repositories/:id/interview`):
  - What to expect.
  - A microphone check: permission, a picker when there's more than one mic, a live level meter, and "we can hear you" once you speak.
  - A test sound for the speakers, and an option to type answers instead.
  - **Start interview** unlocks once the mic has heard you, or straight away in typing mode. Only then is the interview created, because its session token lasts 5 minutes. The token goes to the live page in router state only, never in the URL or browser storage (decision 035).
- **Sign out** from the header (`POST /v1/auth/github/logout`).
- Light and dark themes. Follows the system until you pick one with the toggle.

The live interview and the report are routed, but their screens are not built yet.

Home never reads reports. For an ended interview that has no report, reading one makes Core API trigger grading, which spends real tokens.

## Layout

```
src/
  main.tsx                 fonts, styles, AuthProvider, router
  app/                     router, signed-in layout (header), placeholder pages
  api/                     fetch wrapper (ApiError) and Core API response types
  features/
    auth/                  session context, RequireAuth, landing page
    home/                  home page, recent interviews
    repositories/          list, status chip, connect page, repository page, URL normalising
    interview/             setup page, mic check, level meter, audio/ (browser mic and speakers)
  components/              Button, Card, EmptyState, ProgressBar, Spinner, Logo, ThemeToggle
  hooks/                   useResource, usePolling, useTheme
  styles/                  tokens.css (palette, type, spacing), global.css
  lib/                     formatting
tests/                     Vitest + Testing Library
```

A feature uses another feature only through its `index.ts`. ESLint enforces this. Components use only the variables in `styles/tokens.css`.

## Running locally

Prerequisites: Node 20+, and Core API running on port 8000.

```bash
npm install
npm run dev               # http://localhost:5173
```

Open it on **`localhost`**, not `127.0.0.1`. The GitHub OAuth callback is on `localhost:8000`, and cookies belong to a host, not a port. So the session cookie set there reaches the app only on `localhost:5173`.

Vite proxies `/v1` to Core API, so the browser sees one origin and no CORS setup is needed. The proxy target defaults to `http://127.0.0.1:8000`; set `VITE_CORE_API_URL` in `.env` to change it. After login, Core API redirects to `FRONTEND_BASE_URL` + `/home`, which defaults to `http://localhost:5173`.

## Checks

```bash
npm test                  # Vitest
npm run lint              # ESLint
npm run build             # type check + production build
```
