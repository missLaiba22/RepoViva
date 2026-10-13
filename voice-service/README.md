# Voice Service

Plans each interview's questions in advance, then runs the live interview over a WebSocket, spoken in both directions: questions are synthesized with Deepgram Aura-2 and streamed to the client, and answers are transcribed with Groq Whisper (decisions 043–045, 052).

## What's implemented

- **Question plan** (decisions 052, 057). Core API sends a `plan.requested` job on SQS `planning-jobs` when an interview is created. The worker claims the plan and:
  - asks Repository Service for the repository's largest areas (`/areas`, one per question, up to `MAX_QUESTIONS`),
  - retrieves `PLAN_CHUNKS_PER_AREA` chunks from each area (`filename_prefix` = the area),
  - writes every question in one LLM call (Groq through litellm, decision 038). Questions are scenario-based and never name code (decision 048).

  `plan_status` moves `generating` → `ready` or `failed`. A transient failure (timeout, 429, unusable reply) is retried once automatically. A repository with no code fails as not retryable. A repeated job does nothing once the plan is `ready`; a `failed` plan is replanned, and one left `generating` by a crash reruns when SQS redelivers the message.
- **Admission.** The client sends `session.start {token}` as its first message, never in the URL (decision 035). Voice Service consumes the token once through Core API's `/internal/v1/session-tokens/consume`. A missing, invalid or rejected token closes the socket with code 1008 and one generic reason. A client that sends nothing within 10 s is closed the same way. If the plan isn't `ready`, the client gets `plan_not_ready`, the socket closes with 1008, and the interview is reported `interrupted`.
- **The interview loop.** The planned questions are asked in order: no LLM call and no retrieval during the interview.
- **Speech.**
  - Each question is sent as text first (captions), then as audio streamed chunk by chunk from Deepgram, then `question.audio_end` (decision 044).
  - The client streams microphone audio as binary frames and sends `audio.end`. The buffered answer is compressed to MP3 (about 10x smaller, decision 047) and transcribed in one Groq Whisper call, with the question as prompt so code identifiers come out right (decision 043), and echoed back as `transcript.final`.
  - Silence gets `no_speech` and an answer over `MAX_ANSWER_SECONDS` gets `answer_too_long`. Either way the question waits for another try. Audio is never stored (decision 009).
- **Sessions** (decision 053). One MongoDB document per interview in `interview_sessions`: the plan, and on each question its `status` (`planned` → `asked` → `answered`), answer and per-stage timings (`tts_first_byte_ms`, `tts_ms`, `stt_ms`). A question is marked `asked` before it is sent, so an interrupted interview still records it.
- **Ending** (decision 041):
  - When the plan is used up, or the client sends `session.end`, Voice Service publishes `interview.ended` with outcome `completed` on the EventBridge bus `repoviva` (decision 057). Core API and Evaluation Service each consume it from their own queue. Publishing is retried with backoff.
  - A disconnect or error (including an STT or TTS failure) publishes outcome `interrupted` with an `error_message`.

## Internal endpoints

```
GET  /internal/v1/interviews/{id}/plan    → 200 { interview_id, plan_status, error_message, retryable } · 404
GET  /internal/v1/interviews/{id}/turns   → 200 { turns: [ { seq, question_text, answer_text, status, retrieved_chunk_ids } ] }
```

All HMAC-signed (decision 027).

## Protocol v2

```
Client → Server   session.start {token} · <binary PCM16 16 kHz> · audio.end {}
                  answer.text {text} (typed fallback) · session.end {}
Server → Client   session.ready {interview_id} · question.text {seq, text}
                  <binary PCM16 24 kHz> · question.audio_end {seq}
                  transcript.final {seq, text} · turn.complete {seq}
                  session.end {reason} · error {code, message}
```

Full detail, including close codes: [docs/architecture.md](../docs/architecture.md#websocket--served-by-voice-service).

## Layout

```
src/voice_service/
  main.py                 app wiring; lifespan opens MongoDB
  worker.py               plans interviews from SQS plan.requested jobs
  config.py               settings from env vars
  db.py                   MongoDB client and indexes
  ws.py                   /v1/ws/interview — accepts, wires collaborators, runs the session
  internal/router.py      plan trigger, plan status, turns (HMAC)
  planning/job.py         the planning job: areas → chunks → plan, with retry
  planning/planner.py     the one LLM call and its validation
  planning/prompts.py     planning prompt
  session/runner.py       the interview loop (admission → planned questions → interview.ended)
  clients/events.py       publishes interview.ended
  session/protocol.py     WebSocket message models
  session/store.py        session documents in MongoDB
  clients/core_api.py     consume token, send end-of-session event (HMAC)
  clients/repository.py   list areas, retrieve chunks (HMAC)
  speech/stt.py           PCM → MP3, Groq Whisper transcription
  speech/tts.py           Deepgram Aura-2, streamed PCM
scripts/interview_cli.py  terminal client: mic in, speakers out
```

## Running locally

Prerequisites: MongoDB and LocalStack (`docker compose up -d` from the repo root), with Core API and Repository Service running.

```bash
uv sync
cp .env.example .env        # fill in GROQ_API_KEY, DEEPGRAM_API_KEY and INTERNAL_HMAC_SECRET
uv run uvicorn voice_service.main:app --reload --port 8002
uv run python -m voice_service.worker   # plans interviews from SQS (decision 057)
```

To try an interview:

1. Log in to Core API.
2. `POST /v1/interviews` with a `ready` repository and copy the `session_token`. It expires after 5 minutes.
3. Wait a few seconds for the plan (the log says "plan of N questions ready"), then run:

```bash
uv run python scripts/interview_cli.py <session_token>
```

Each question prints and plays through your speakers. When it finishes, press Enter to start recording and Enter again to send. Type `/t <answer>` to answer by typing, or `/end` to stop early.

## Tests

```bash
uv run pytest
```

The runner tests drive the whole loop with fake collaborators, and the planning tests drive the job with fakes: no network, database, LLM, STT or TTS. `tests/test_session_store.py` runs against a real MongoDB and is skipped when none is reachable.

## Environment variables

| Variable | Purpose |
|---|---|
| `MONGODB_URI` | e.g. `mongodb://127.0.0.1:27017` |
| `MONGODB_DATABASE` | default `repoviva_voice` |
| `CORE_API_BASE_URL` | e.g. `http://127.0.0.1:8000` |
| `REPOSITORY_SERVICE_BASE_URL` | e.g. `http://127.0.0.1:8001` |
| `INTERNAL_HMAC_SECRET` | Must match the other services (decision 027) |
| `GROQ_API_KEY` | Free key from console.groq.com |
| `LLM_MODEL` | litellm model string, default `groq/qwen/qwen3.8-27b` |
| `STT_MODEL` | litellm transcription model, default `groq/whisper-large-v3-turbo` |
| `DEEPGRAM_API_KEY` | Deepgram key for TTS (new accounts get $200 credit) |
| `TTS_VOICE` | Deepgram voice, default `aura-2-thalia-en` |
| `MAX_ANSWER_SECONDS` | Longest accepted spoken answer, default 180 |
| `MAX_QUESTIONS` | Questions (and areas) per interview, default 6 |
| `SESSION_START_TIMEOUT_S` | Wait for `session.start`, default 10 |
| `PLAN_CHUNKS_PER_AREA` | Chunks retrieved per area for planning, default 2 |

## What's next

- **Measure the planning call** (tokens, logged per plan) against the ~5,000 estimate, and the turn latency against the baseline, using the session documents' timings.
