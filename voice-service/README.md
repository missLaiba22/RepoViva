# Voice Service

Runs RepoViva's live interview over a WebSocket. **Current slice: text in, text out** (decision 039). The loop is complete; STT and TTS slot in around it in the next slice.

## What's implemented

- **Admission.** The client sends `session.start {token}` as its first message, never in the URL (decision 035). Voice Service consumes the token once through Core API's `/internal/v1/session-tokens/consume`. A missing, invalid or rejected token closes the socket with code 1008 and one generic reason. A client that sends nothing within 10 s is closed the same way.
- **The interview loop.** Each turn retrieves code from Repository Service, generates a question with Groq through litellm (decisions 034, 038), persists it, and asks it.
  - The opening question uses a fixed architecture seed query.
  - Each follow-up queries with the previous question plus the answer, excluding chunks already used (decision 042).
- **Turns.** Turns are stored in Voice Service's own `turns` table (decision 040). A turn is inserted as `asked` before the question is sent, then marked `answered`. Each turn records its retrieved chunk IDs and the time spent on retrieval and on the LLM.
- **Ending** (decision 041):
  - After `MAX_QUESTIONS` answers, or when the client sends `session.end`, Voice Service sends `interview.completed` to Core API.
  - A disconnect or error sends `interview.interrupted` with an `error_message`.

## Protocol v1

```
Client → Server   session.start {token} · answer.text {text} · session.end {}
Server → Client   session.ready {interview_id} · question.text {turn_id, seq, text}
                  turn.complete {turn_id} · session.end {reason} · error {code, message}
```

Full detail, including close codes: [docs/architecture.md](../docs/architecture.md#websocket--served-by-voice-service).

## Layout

```
src/voice_service/
  ws.py                   /v1/ws/interview — accepts, wires collaborators, runs the session
  session/runner.py       the interview loop (admission → turns → end event)
  session/protocol.py     WebSocket message models
  session/turns.py        turns persistence
  clients/core_api.py     consume token, send end-of-session event (HMAC)
  clients/repository.py   retrieve chunks (HMAC)
  llm/prompts.py          interviewer prompt + seed query
  llm/generator.py        question generation via litellm
sql/schema.sql            turns DDL, applied at startup
scripts/interview_cli.py  terminal client for manual runs
```

## Running locally

Prerequisites: Postgres (`docker compose up -d` from the repo root), with Core API and Repository Service running.

```bash
uv sync
cp .env.example .env        # fill in GROQ_API_KEY and INTERNAL_HMAC_SECRET
uv run uvicorn voice_service.main:app --reload --port 8002
```

To try an interview:

1. Log in to Core API.
2. `POST /v1/interviews` with a `ready` repository and copy the `session_token`. It expires after 5 minutes.
3. Run:

```bash
uv run python scripts/interview_cli.py <session_token>
```

Answer each question and press Enter, or type `/end` to stop early.

## Tests

```bash
uv run pytest
```

The runner tests drive the whole loop with fake collaborators: no network, database or LLM.

## Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql://...` (asyncpg scheme) |
| `CORE_API_BASE_URL` | e.g. `http://localhost:8000` |
| `REPOSITORY_SERVICE_BASE_URL` | e.g. `http://localhost:8001` |
| `INTERNAL_HMAC_SECRET` | Must match the other services (decision 027) |
| `GROQ_API_KEY` | Free key from console.groq.com |
| `LLM_MODEL` | litellm model string, default `groq/llama-3.3-70b-versatile` |
| `MAX_QUESTIONS` | Questions per interview, default 6 |
| `SESSION_START_TIMEOUT_S` | Wait for `session.start`, default 10 |
| `RETRIEVAL_TOP_K` | Chunks per question, default 6 |

## What's next

- **Audio slice:** choose STT and TTS providers, replace `answer.text` with `audio.chunk`/`audio.end`, and stream `question.audio_chunk`.
- **Evaluation Service:** build reports from `turns`.
