# Voice Service

Plans each interview's questions in advance, then runs the live interview over a WebSocket: questions are spoken with Deepgram Aura-2, answers transcribed with Groq Whisper. How it fits in: [docs/architecture.md](../docs/architecture.md).

## Responsibilities

- **Question plan** (decisions 052, 057): on a `plan.requested` job, the worker gets the repository's largest areas (up to `MAX_QUESTIONS`), retrieves a few chunks from each, and writes all questions in one LLM call (capped at 800 output tokens). Questions are scenario-based and never name code (decision 048). Status: `generating → ready | failed`; transient failures retry once.
- **Admission:** the client sends its session token as the first message, never in the URL (decision 035). The token is burned once through Core API. A bad token, a 10 s silence, or a plan that isn't ready closes the socket with 1008.
- **Interview:** the planned questions are asked in order, with no LLM call during the session. `session.ready` carries `question_count` for "Question N of M" (decision 062). A session ends after `MAX_SESSION_SECONDS` (30 min, decision 059).
- **Speech:** each question is sent as text, then streamed audio. The answer's audio is compressed to MP3 and transcribed in one call, with the question as prompt so identifiers come out right (decisions 043–047). Audio is never stored.
- **Sessions:** one MongoDB document per interview with the plan, each answer and per-stage timings (decision 053).
- **Ending:** publishes `interview.ended` with outcome `completed` or `interrupted` (decision 041).

## API

| Endpoint | Notes |
|---|---|
| `WS /v1/ws/interview` | The live interview (protocol below) |
| `GET /internal/v1/interviews/{id}/plan` | HMAC. Plan status |
| `GET /internal/v1/interviews/{id}/turns` | HMAC. Questions and answers, for grading |
| `GET /health` | Liveness |

**WebSocket protocol v2**

```
Client → Server   session.start {token} · <PCM16 16 kHz> · audio.end · answer.text {text} · session.end
Server → Client   session.ready {interview_id, question_count} · question.text {seq, text}
                  <PCM16 24 kHz> · question.audio_end {seq} · transcript.final {seq, text}
                  turn.complete {seq} · session.end {reason} · error {code, message}
```

Close codes and details: [architecture](../docs/architecture.md#websocket--served-by-voice-service).

## Messaging

| | Where | Message |
|---|---|---|
| Consumes | `planning-jobs` queue | `plan.requested` |
| Publishes | `repoviva` bus | `interview.ended` |

## Run locally

Needs MongoDB and LocalStack (`docker compose up -d`), with Core API and Repository Service running.

```bash
uv sync
cp .env.example .env
uv run uvicorn voice_service.main:app --reload --port 8002
uv run python -m voice_service.worker
```

To try an interview without the frontend, create one through Core API and run `uv run python scripts/interview_cli.py <session_token>` (mic in, speakers out; `/t <answer>` to type, `/end` to stop).

## Configuration

| Variable | Purpose |
|---|---|
| `MONGODB_URI`, `MONGODB_DATABASE` | Sessions store |
| `CORE_API_BASE_URL`, `REPOSITORY_SERVICE_BASE_URL` | Token consume, areas and retrieval |
| `INTERNAL_HMAC_SECRET` | Same value in every service |
| `GROQ_API_KEY` | Planning LLM and STT |
| `DEEPGRAM_API_KEY` | TTS |
| `LLM_MODEL`, `STT_MODEL`, `TTS_VOICE` | Defaults: `qwen3.8-27b`, `whisper-large-v3-turbo`, `aura-2-thalia-en` |
| `MAX_QUESTIONS` | Questions per interview (default 6) |
| `MAX_ANSWER_SECONDS` | Longest spoken answer (default 180) |
| `MAX_SESSION_SECONDS` | Longest session (default 1800) |
| `AWS_*`, `EVENT_BUS_NAME`, `PLANNING_JOBS_QUEUE_URL` | SQS and EventBridge; see `.env.example` |

## Tests

```bash
uv run ruff check . && uv run pytest
```

Runner and planning tests use fakes (no network, LLM or speech). `tests/test_session_store.py` needs a real MongoDB and is skipped without one.
