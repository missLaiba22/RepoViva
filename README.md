# RepoViva

A voice-based interview coach for developers. Connect a GitHub repository, and RepoViva studies the actual code, then runs a spoken mock interview grounded in that code — asking questions, following up on your answers, and producing a feedback report at the end.

## Why

Developers prepare with generic interview questions but often struggle to explain and defend the projects they actually built. RepoViva lets you practise talking about your own code.

## Architecture

Four Python microservices in a monorepo, sharing one PostgreSQL + pgvector database (each service owns its own tables). Internal calls are HMAC-signed HTTP.

```mermaid
flowchart LR
    FE[Browser<br/>React SPA planned]

    subgraph Built
        CORE[Core API<br/>auth · repos · interviews]
        REPO[Repository Service<br/>ingest · retrieve]
        VOICE[Voice Service<br/>spoken interview loop]
    end

    subgraph Planned
        EVAL[Evaluation Service<br/>reports]
    end

    DB[(PostgreSQL<br/>+ pgvector)]
    GH[GitHub]
    VOY[Voyage AI<br/>embeddings]
    LLM[Groq<br/>question LLM · Whisper STT]
    TTS[Deepgram<br/>Aura-2 TTS]
    AI[Report LLM<br/>TBD]

    FE -- REST --> CORE
    FE -- WebSocket --> VOICE
    CORE -- OAuth --> GH
    CORE -- ingest trigger --> REPO
    REPO -- status events --> CORE
    REPO -- clone --> GH
    REPO -- embed --> VOY
    VOICE -- consume token · lifecycle events --> CORE
    VOICE -- retrieve code --> REPO
    VOICE -- questions · transcribe --> LLM
    VOICE -- synthesize --> TTS
    EVAL -.-> AI
    CORE --> DB
    REPO --> DB
    VOICE --> DB
    EVAL -.-> DB
```

*Solid lines are implemented; dashed lines are planned.*

| Service | Role | Status |
|---|---|---|
| [core-api](core-api/) | GitHub OAuth, users, repositories, interviews, report metadata | Auth, repositories, interviews (create, list, get), session-token consumption and lifecycle events implemented |
| [repository-service](repository-service/) | Clone, chunk, embed and retrieve repository code | Ingestion and retrieval implemented |
| [voice-service](voice-service/) | Live interview over WebSocket (STT → retrieval → LLM → TTS) | Spoken interview loop implemented (Groq Whisper STT, Deepgram TTS); terminal mic client |
| evaluation-service | Generates the end-of-interview report | Not started |
| frontend | React + Vite + TypeScript SPA | Not started |

Details: [docs/architecture.md](docs/architecture.md). The reasoning behind every choice: [docs/decisions.md](docs/decisions.md).

## Tech stack

- **Backend:** Python 3.11+, FastAPI, `uv`, pytest, ruff
- **Database:** PostgreSQL 16 + pgvector (Docker Compose locally)
- **Ingestion:** CocoIndex (syntax-aware chunking), Voyage `voyage-4-lite` embeddings
- **Frontend:** React + Vite + TypeScript (planned)
- **Interview LLM:** Groq `llama-3.3-70b-versatile` via litellm (decision 038)
- **STT:** Groq `whisper-large-v3-turbo` (decision 043)
- **TTS:** Deepgram Aura-2, streamed (decision 044)

## Running locally

Prerequisites: Python 3.11+, [`uv`](https://docs.astral.sh/uv/), Docker, Git.

```bash
# 1. Start Postgres (pgvector)
docker compose up -d

# 2. Start each service — see its README for .env setup
cd core-api && uv sync && uv run alembic upgrade head && uv run uvicorn core_api.main:app --reload --port 8000
cd repository-service && uv sync && uv run uvicorn repository_service.main:app --reload --port 8001
cd voice-service && uv sync && uv run uvicorn voice_service.main:app --reload --port 8002
```

All services must share the same `INTERNAL_HMAC_SECRET`.

## Project status

Working end to end: GitHub login → submit a repository → background ingestion (clone, chunk, embed) with status callbacks → retrieval over the indexed code → create an interview and receive a single-use session token → the token is consumed through Core API, which starts the interview.

Implemented, tested with fakes, live run pending: the text-mode interview in Voice Service. It covers WebSocket admission with the token, code-grounded questions from Groq, persisted turns, and completed/interrupted reported back to Core API. Try it with `voice-service/scripts/interview_cli.py`.

Next: Evaluation Service and the frontend.
