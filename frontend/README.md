# Frontend

RepoViva's web app: React + Vite + TypeScript (decision 017). It talks to Core API over REST with the session cookie, and talks to Voice Service over a WebSocket for the live interview (decision 022).

## What's implemented

- **Landing page** (`/`): the headline, **Sign in with GitHub**, and a still preview of the interview screen.
- **Sidebar** on every signed-in page except the live interview:
  - **Connect repository** at the top.
  - **Repositories**, with each repository listed underneath with a status dot (ready, preparing, import failed) and a count while any is preparing. The list refreshes when a repository is connected or retried, and every 3 s while one is preparing.
  - **Reports**.
  - An account menu (GitHub avatar and name) with the theme switch and **Sign out**.
  - On narrow screens it becomes a top bar, without the repository list.
- **Repositories** (`/repositories`; `/home`, where Core API sends you after sign-in, redirects here):
  - One compact card per repository: name, GitHub path, status (**Ready to practice**, **Preparing**, **Import failed**), interview count and date added. While any is preparing, the list refreshes every 3 s.
  - **Start interview** on ready repositories. A failed one says "Couldn't prepare this repository." with **Retry** and **Details** (the raw `error_message`, hidden until opened).
- **Reports** (`/interviews`): every interview taken (completed, ended early, in progress), with **View report** once it has ended.
- **Connect a repository** (`/repositories/new`):
  - One link field. It accepts what people paste: `owner/repo`, `github.com/owner/repo`, `.git` URLs and links deeper into a repository. It shows the URL it will send.
  - A repository you've already connected (Core API's 409) opens that repository instead of showing an error.
- **Repository page** (`/repositories/:id`):
  - While indexing: a progress bar, refreshed every 2 s.
  - When ready: **Start interview**.
  - When failed: a one-line reason, **Retry** (or **Connect a different repository** when retrying can't help), and **Details**.
- **Interview setup** (`/repositories/:id/interview`):
  - What to expect.
  - A microphone check: permission, a picker when there's more than one mic, a live level meter, and "we can hear you" once you speak.
  - A test sound for the speakers, and an option to type answers instead.
  - **Start interview** unlocks once the mic has heard you, or straight away in typing mode. Only then is the interview created, because its session token lasts 5 minutes. The token goes to the live page in router state only, never in the URL or browser storage (decision 035).
- **Live interview** (`/interviews/:id/live`), a focused page without the sidebar:
  - Connects to Voice Service's WebSocket (protocol v2). The token is sent as the first message, never in the URL.
  - The question is shown as text and played as it streams in (PCM16 24 kHz, Web Audio). It can be replayed, or skipped once all its audio has arrived.
  - **Tap to answer, tap to send.** The mic audio is resampled to PCM16 16 kHz in the browser (an AudioWorklet plus `audio/pcm.ts`) and sent in 100 ms chunks, then `audio.end`. Recording stops on its own at 175 s, just under the server's 180 s limit.
  - Shows "What we heard" after each answer. "No speech" and similar errors hand the turn back with a short note.
  - **Type instead** at any turn (`answer.text`), or for the whole interview if typing was chosen in setup or the mic can't open.
  - **End interview** asks first, then sends `session.end`, so it still counts as completed. Leaving the page also asks first. Closing the tab ends the interview as interrupted, with a partial report.
  - End screens: complete, ended early, interrupted (answers kept), session expired or reused (close 1008), and "can't be reopened" after a reload.
- **Report** (`/interviews/:id/report`):
  - An overall score (the mean of average correctness and clarity, 1–5), both averages, and how many questions were answered, with **What went well** and **Work on next**.
  - **Strong answers** (both scores 4 or more), **Answers to revisit**, **Files to revisit** (each linking to GitHub) and **Not reached**.
  - Each answer opens to your answer, both scores with their reasons, strengths and gaps, and **What a strong answer covers**. Each key point links to the exact lines on GitHub.
  - While grading: a progress state, refreshed every 4 s.
  - If grading failed: **Try grading again** (`POST /v1/interviews/{id}/report/retry`).
  - Links point at the default branch (`blob/HEAD`), so they show today's code, which may have changed since indexing.
- **Sign out** from the account menu (`POST /v1/auth/github/logout`).
- Light and dark themes. Follows the system until you pick one with the toggle.

The Repositories and Reports pages never read reports. For an ended interview that has no report, reading one makes Core API trigger grading, which spends real tokens.

## Layout

```
src/
  main.tsx                 fonts, styles, AuthProvider, router
  app/                     router, signed-in layout (sidebar, repository list, account menu), not-found page
  api/                     fetch wrapper (ApiError) and Core API response types
  features/
    auth/                  session context, RequireAuth, landing page
    repositories/          repositories page and cards, status chip, connect page, repository page, URL normalising
    report/                reports page, report page, summary, question list, source links
    interview/             setup page, mic check, level meter
      audio/               mic check, capture (PCM16 16 kHz), question player, pcm maths
      live/                live page, protocol, state reducer, socket hook
  components/              Button, Card, EmptyState, ErrorDetails, Facts, Icon, InterviewList, PageHeader, ProgressBar,
                           RepoName, ScoreBar, Spinner, Logo, ThemeToggle
  hooks/                   useResource, usePolling, useTheme
  styles/                  tokens.css (palette, type, spacing), global.css
  lib/                     formatting, breadcrumbs, interview facts
tests/                     Vitest + Testing Library
```

A feature uses another feature only through its `index.ts`. ESLint enforces this. Components use only the variables in `styles/tokens.css`.

## Running locally

Prerequisites: Node 20+, with Core API on port 8000. For interviews, also Repository Service on 8001 and Voice Service on 8002.

```bash
npm install
npm run dev               # http://localhost:5173
```

Open it on **`localhost`**, not `127.0.0.1`. The GitHub OAuth callback is on `localhost:8000`, and cookies belong to a host, not a port. So the session cookie set there reaches the app only on `localhost:5173`.

Vite proxies `/v1` to Core API and `/v1/ws` (the interview WebSocket) to Voice Service, so the browser sees one origin and no CORS setup is needed. The targets default to `http://127.0.0.1:8000` and `http://127.0.0.1:8002`; set `VITE_CORE_API_URL` and `VITE_VOICE_SERVICE_URL` in `.env` to change them. After login, Core API redirects to `FRONTEND_BASE_URL` + `/home` (which opens Repositories); the base URL defaults to `http://localhost:5173`.

## Checks

```bash
npm test                  # Vitest
npm run lint              # ESLint
npm run build             # type check + production build
```
