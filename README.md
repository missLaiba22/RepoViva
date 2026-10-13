# RepoViva

A voice-based interview coach for developers. Connect a GitHub repository; RepoViva studies the code, runs a spoken mock interview about it, and grades your answers in a report.

## Why

Developers prepare with generic interview questions but struggle to explain the projects they actually built. RepoViva lets you practise talking about your own code.

## How it works

1. **Ingest:** the repository is cloned, chunked and embedded (pgvector).
2. **Plan:** when you start an interview, one scenario question is written per major area of the code.
3. **Interview:** questions are spoken (TTS), your answers transcribed (STT), over a WebSocket.
4. **Report:** each answer is scored for correctness and clarity against the code it was asked about, with key points citing your files.

## Architecture

Four Python services in a monorepo. Each owns its data and talks to the others in one of three ways (decision 057):

- **Queries** (the caller needs the answer): HMAC-signed HTTP.
- **Jobs** ("do X"): an SQS queue, consumed by the owning service's worker.
- **Events** ("X happened"): the EventBridge bus `repoviva`, routed to one SQS queue per consumer.

Every queue has a dead-letter queue, and every job is idempotent, so a crashed job is retried by redelivery.

```mermaid
flowchart LR
    FE[Browser<br/>React SPA]
    CORE[Core API<br/>auth · repos · interviews]
    REPO[Repository Service<br/>ingest · retrieve]
    VOICE[Voice Service<br/>plan · live interview]
    EVAL[Evaluation Service<br/>grading · reports]

    FE -- REST --> CORE
    FE -- WebSocket --> VOICE
    CORE -. ingestion job .-> REPO
    REPO -. ingestion.* .-> CORE
    CORE -. plan job .-> VOICE
    VOICE -. interview.ended .-> CORE
    VOICE -. interview.ended .-> EVAL
    CORE -. report job .-> EVAL
    VOICE -- areas · retrieve --> REPO
    EVAL -- turns --> VOICE
    EVAL -- chunks --> REPO
```

*Solid: HTTP queries (only the main ones shown). Dotted: SQS jobs and EventBridge events.*

| Service | Owns | Data |
|---|---|---|
| [core-api](core-api/) | GitHub OAuth, users, repositories, interviews; the frontend's only REST API | Postgres |
| [repository-service](repository-service/) | Clone, chunk, embed, retrieve | Postgres + pgvector |
| [voice-service](voice-service/) | Question planning and the live interview | MongoDB |
| [evaluation-service](evaluation-service/) | Grading and reports | Postgres |
| [frontend](frontend/) | React + Vite + TypeScript SPA | — |

Each backend service runs an API and a worker from the same code. Details: [docs/architecture.md](docs/architecture.md); reasoning: [docs/decisions.md](docs/decisions.md).

## Tech stack

- **Backend:** Python 3.11+, FastAPI, `uv`, pytest, ruff; shared infrastructure in [`libs/repoviva-common`](libs/repoviva-common/)
- **Messaging:** AWS SQS + EventBridge via `boto3`; LocalStack locally
- **Data:** PostgreSQL 16 + pgvector, MongoDB
- **Ingestion:** CocoIndex chunking, Voyage `voyage-4-lite` embeddings
- **LLMs (Groq):** `qwen/qwen3.8-27b` for question planning, `openai/gpt-oss-120b` for grading
- **Speech:** Groq Whisper (STT), Deepgram Aura-2 (TTS)

## Running locally

Prerequisites: Python 3.11+, [`uv`](https://docs.astral.sh/uv/), Docker, Node.js, Git. Copy each service's `.env.example` to `.env` and fill it in; all services share one `INTERNAL_HMAC_SECRET`.

```bash
# Postgres, MongoDB and LocalStack (creates the queues, bus and rules)
docker compose up -d

# Each service runs an API and a worker; give each command its own terminal
cd core-api && uv sync && uv run alembic upgrade head
cd core-api && uv run uvicorn core_api.main:app --port 8000
cd core-api && uv run python -m core_api.worker
cd repository-service && uv run uvicorn repository_service.main:app --port 8001
cd repository-service && uv run python -m repository_service.worker
cd voice-service && uv run uvicorn voice_service.main:app --port 8002
cd voice-service && uv run python -m voice_service.worker
cd evaluation-service && uv run uvicorn evaluation_service.main:app --port 8003
cd evaluation-service && uv run python -m evaluation_service.worker

# Web app: open http://localhost:5173
cd frontend && npm install && npm run dev
```

On Windows, use `127.0.0.1` rather than `localhost` in service URLs (`localhost` adds about 2 s per call).

## Status

Built: GitHub login → ingestion → question plan → spoken interview → graded report. Each step has been run against LocalStack; a full browser run with the new question plan is next.

Limits:
- Public GitHub repositories only.
- Groq's free tier fits one live interview at a time and about 10 reports a day.
- The live page doesn't yet wait for the question plan to be ready (decision 052).
- Runs locally; not deployed, no CI.

Next: the live page's "Preparing your interview…" state, then deployment on AWS (ECS, IAM, DLQ alarms).
