# Architecture

## Overview

RepoViva is built as **4 microservices** communicating over HTTP (and WebSocket for the interview session). Requirements, core entities, service split, and key architectural constraints have been decided. Specific external providers (STT, TTS, LLM) and the full data model are still open.

This document is the source of truth for the current architecture. See `decisions.md` for the reasoning behind each choice.

## Architecture Diagram

```mermaid
flowchart TB
    subgraph "Client"
        FE[React SPA]
    end

    subgraph "Backend Services"
        CORE[Core API<br/>Auth + CRUD]
        REPO[Repository Service<br/>Ingest + Retrieve]
        VOICE[Voice Service<br/>Interview session]
        EVAL[Evaluation Service<br/>Reports]
    end

    DB[(PostgreSQL<br/>+ pgvector)]

    subgraph "External Providers"
        GH[GitHub<br/>OAuth + Repos]
        LLM[LLM Provider<br/>TBD]
        STT[STT Provider<br/>TBD]
        TTS[TTS Provider<br/>TBD]
    end

    FE -- REST --> CORE
    FE -- WebSocket --> VOICE

    CORE -- trigger ingest --> REPO
    REPO -. status callback<br/>(deferred, see decision 028) .-> CORE
    CORE -- trigger report --> EVAL
    VOICE -- retrieval query --> REPO

    CORE --> DB
    REPO --> DB
    VOICE --> DB
    EVAL --> DB

    CORE -- OAuth --> GH
    REPO -- fetch repo --> GH
    REPO -- embeddings --> LLM
    VOICE -- transcribe --> STT
    VOICE -- generate --> LLM
    VOICE -- synthesize --> TTS
    EVAL -- generate --> LLM
```

*The status-callback arrow is dashed to signal that this direction is designed but not implemented — see decision 028.*

## Components

### Core API service

Main REST entry point for the frontend. Owns:

- GitHub OAuth flow and session management
- User records
- Repository metadata (with ingestion status)
- Interview metadata (creation, listing, session token issuance)
- Report metadata (listing, retrieval — actual generation delegated to Evaluation Service)

Delegates:

- Ingestion trigger → Repository Service
- Report generation trigger → Evaluation Service
- Live interview session (WebSocket) → Voice Service

### Repository Service

Owns everything about a repository's code and its searchable representation:

- Fetches the repository from GitHub
- Parses, chunks, and embeds source code
- Persists chunks + embeddings (pgvector) to the shared database
- Exposes a retrieval endpoint used by Voice Service during interviews
- (Planned, see decision 028) Reports ingestion progress to Core API via authenticated callbacks

Runs ingestion asynchronously (long-running work; must not block API requests). See "Data Flow" below.

### Voice Service

Owns the live interview session:

- Terminates the WebSocket from the frontend
- Runs the STT → Repository Service lookup → LLM → TTS pipeline for each turn
- Persists each turn as it completes (question + transcribed answer)
- Handles session interruption gracefully (partial report is possible because turns are already persisted)

### Evaluation Service

Given a completed interview transcript, generates the final report:

- Called by Core API when an interview ends (or on partial-report request)
- Calls the LLM provider for report generation
- Writes the report to the shared database

Kept separate so report generation (potentially slow, batchable) does not compete with live-session latency.

### PostgreSQL (shared, with pgvector)

Single database, four schemas (one per service). Each service owns its own tables — no service reads or writes another service's tables directly. Cross-service data access goes through HTTP APIs.

## Core Entities

- **User** — the developer using RepoViva.
- **Repository** — a GitHub repo the user has connected.
- **Interview** — a mock interview session against a repository.
- **Turn** — one question and its answer, treated as a single unit.
- **Report** — the evaluation output at the end of an interview.

Fields per entity are deferred until each service's implementation clarifies exactly what state it must hold.

## API Surface

### REST — served by Core API (v1)

Auth
```
GET  /v1/auth/github/login       generates state cookie, redirects to GitHub
GET  /v1/auth/github/callback    validates state, exchanges code, sets session cookie
GET  /v1/me                      returns the current user (requires session cookie)
```

Repositories
```
POST /v1/repositories            body: { github_url }  → Repository (status=queued or failed)
GET  /v1/repositories            list current user's repos
GET  /v1/repositories/{id}       single repo, including ingestion status
```

Interviews
```
POST /v1/interviews              body: { repository_id }  → Interview + session token
                                 (only allowed if repo status = ready)
GET  /v1/interviews              list current user's interviews
GET  /v1/interviews/{id}         single interview
GET  /v1/interviews/{id}/report  the report
```

The current user is always derived from the auth token, never from request bodies.

### Internal service-to-service APIs

These are called only by other services, never exposed to the frontend. All internal calls are authenticated with HMAC-SHA256 (see decision 027).

**Implemented (slice 2 step 4):**

Core API → Repository Service (ingestion trigger)
```
POST /internal/v1/repositories/{repository_id}/ingest
body: { github_url: string }
→ 202 Accepted (fire-and-forget from Core API's perspective)
→ 401 Unauthorized (missing or invalid HMAC signature)
```

**Designed but deferred (see decision 028):**

Repository Service → Core API (status callback)
```
POST /internal/v1/repositories/{repository_id}/events
body: {
  event_id:    <uuid v4>,
  event_type:  "ingestion.started" | "ingestion.completed" | "ingestion.failed",
  occurred_at: <ISO 8601 timestamp, UTC>,
  data:        { ... }   // shape depends on event_type
}

Response codes (planned):
- 202 Accepted — event received and processed
- 409 Conflict — event_id already seen (safe replay, no side effects)
- 422 Unprocessable Entity — illegal state transition
- 401 — missing or invalid HMAC signature
- 404 — unknown repository_id
```

**Planned for later slices:**

Voice Service → Repository Service (retrieval)
```
POST /internal/v1/retrieve
```
Returns top-K relevant code chunks for a query + repo. Detailed shape TBD.

Core API → Evaluation Service (report generation)
```
POST /internal/v1/reports
```
Generates a report for a completed (or partial) interview. Detailed shape TBD.

### WebSocket — served by Voice Service

Interview turns are not REST. Once an interview is created by Core API, the client connects a WebSocket to the Voice Service, presenting the session token issued by Core API.

First-sketch message protocol (to be refined during implementation):

Client → Server
- `session.start` (with interview_id + session token)
- `audio.chunk` (binary audio frames as user speaks)
- `audio.end` (optional client-side end-of-speech hint)

Server → Client
- `session.ready`
- `transcript.partial` / `transcript.final` (STT results for UI feedback)
- `question.text` (the question in text form for display / accessibility)
- `question.audio_chunk` (TTS audio streaming down)
- `turn.complete` (turn persisted)
- `session.end`
- `error`

## Data Flow

### Repository ingestion (current state — slice 2 step 4)

Ingestion is triggered synchronously and runs asynchronously inside Repository Service. Status reporting back to Core API is not implemented — see decision 028.

1. User submits a GitHub URL via `POST /v1/repositories` (Core API).
2. Core API validates the URL, creates a Repository row with status `queued`, and calls Repository Service's `POST /internal/v1/repositories/{id}/ingest` (HMAC-signed) with the GitHub URL in the body.
3. Repository Service verifies the HMAC signature and returns `202 Accepted` immediately. (Real ingestion work is not yet implemented — Repository Service currently acknowledges and does nothing further.)
4. If the trigger call fails (network error, timeout, non-2xx response), Core API marks the just-created row `failed` immediately with an `error_message` describing the failure, and returns 201 with that row. The user sees the row as `failed` right away.
5. Core API returns the created (or immediately-failed) Repository row to the client with a 201 response.
6. Client polls `GET /v1/repositories/{id}` to observe the current status. In the current architecture, once the row is `queued` it stays there until decision 028 is revisited — the frontend has no visibility into real ingestion progress.

The event-callback protocol described in decisions 024–026 is a designed-but-unimplemented option. When ingestion status visibility is needed, that design (or a message-broker alternative) will be implemented.

### Interview session (live, over WebSocket)

1. Client calls `POST /v1/interviews` on Core API (allowed only if repo status is `ready`). Core API creates the interview and returns a session token.
2. Client opens a WebSocket to Voice Service, presenting the session token.
3. Voice Service validates the token, retrieves repo context via Repository Service's `/internal/v1/retrieve`, generates the opening question via the LLM provider, and streams TTS audio down.
4. User speaks. Client streams audio frames up. Voice Service runs STT and VAD on the incoming stream.
5. On end-of-speech, Voice Service persists the completed turn (question + transcript), then queries Repository Service for context relevant to the user's answer, generates the next question via the LLM, and streams TTS down.
6. Loop until the interview ends.
7. On session end (normal or interrupted), Voice Service (or Core API) calls Evaluation Service to generate a report from all completed turns.

## Data Storage

- **PostgreSQL (shared, with pgvector)** — one database, per-service schemas:
  - Core API schema: users, repositories (metadata + status), interviews, encrypted OAuth tokens, reports (metadata). *When decision 028 is revisited and callbacks are implemented, a table for processed inbound event IDs will be added.*
  - Repository Service schema: code chunks, embeddings, repository index state.
  - Voice Service schema: turns.
  - Evaluation Service schema: report content.
- **No raw audio storage** — audio is discarded after transcription.

## Current Constraints

- Single-region deployment is acceptable for MVP.
- Target scale: ~10 concurrent active interviews.
- Interview turn latency target: 4–5s p95 (aspirational 3s). Inter-service network hops eat some of this budget — see decisions 006 and 020.
- Ingestion target for small repos (<100 files): under 1 minute p95.
- Voice pipeline is DIY over a WebSocket; Voice Service orchestrates each stage (STT, retrieval, LLM, TTS) itself.
- User isolation is enforced at the data-access layer in Core API via a `get_current_user` dependency on protected routes, and at the service layer via queries always scoped by `owner_user_id`. `/health` and auth endpoints are the only unauthenticated routes.
- OAuth tokens are encrypted at the application layer (Core API). Everything else relies on disk-level encryption.
- Shared database across services with strict per-service table ownership (see decision 021).
- No API gateway — frontend calls Core API and Voice Service directly (see decision 022).
- Internal service-to-service HTTP calls are authenticated with HMAC-SHA256 over `timestamp + "." + body`, with a 60-second freshness window and a single shared secret (see decision 027). Each service implements its own HMAC module ("write it twice, deliberately") — the wire format is the contract.
- Ingestion status is *not* observable end-to-end in the current implementation (see decision 028). A repository row only ever transitions to `failed` if the trigger call itself fails; real ingestion progress is invisible until callbacks or a message broker is implemented.

## Future Evolution

Open decisions that will shape architecture:

- Choice of STT, TTS, and LLM providers
- Choice of background job system inside Repository Service (real ingestion work — the trigger endpoint currently acknowledges without doing anything)
- Ingestion status reporting mechanism (HTTP callbacks per decisions 024–026, or a message broker) — see decision 028
- Choice of managed Postgres provider (Supabase or Neon)
- Full data model (fields per entity, per-service schemas)
- Final WebSocket message protocol
- Retry semantics for failed ingestions (retry-in-place vs new row)
- Logout endpoint (deferred — no state to clean up server-side, so it's a cookie-clear + redirect when needed)
- Whether to migrate from signed cookies to JWTs if the session payload grows
- Naming convention on `Base.metadata` to stop Alembic autogenerate from re-detecting constraint drift on every run (small cleanup after slice 2)

Deferred but named in `decisions.md`:

- Migrating from DIY voice pipeline to a realtime voice API if latency proves insufficient
- Live session resumption when partial reports prove too limiting
- Broader application-level encryption if the threat model changes
- Per-service databases if shared-DB coupling causes real problems