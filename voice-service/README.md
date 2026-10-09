# Voice Service

Runs RepoViva's live interview over a WebSocket, spoken in both directions: questions are synthesized with Deepgram Aura-2 and streamed to the client, and answers are transcribed with Groq Whisper (decisions 043–045).

## What's implemented

- **Admission.** The client sends `session.start {token}` as its first message, never in the URL (decision 035). Voice Service consumes the token once through Core API's `/internal/v1/session-tokens/consume`. A missing, invalid or rejected token closes the socket with code 1008 and one generic reason. A client that sends nothing within 10 s is closed the same way.
- **The interview loop.** Each turn retrieves code from Repository Service, generates a question with Groq through litellm (decisions 034, 038), persists it, and asks it.
  - The opening question uses a fixed architecture seed query.
  - Each follow-up queries with the previous question plus the answer, excluding chunks already used (decision 042).
- **Speech.**
  - Each question is sent as text first (captions), then as audio streamed chunk by chunk from Deepgram, then `question.audio_end` (decision 044).
  - The client streams microphone audio as binary frames and sends `audio.end`. The buffered answer is compressed to MP3 (about 10x smaller, decision 047) and transcribed in one Groq Whisper call, with the question as prompt so code identifiers come out right (decision 043), and echoed back as `transcript.final`.
  - Silence gets `no_speech` and an answer over `MAX_ANSWER_SECONDS` gets `answer_too_long`. Either way the turn waits for another try. Audio is never stored (decision 009).
- **Turns.** Turns are stored in Voice Service's own `turns` table (decision 040). A turn is inserted as `asked` before the question is sent, then marked `answered`. Each turn records its retrieved chunk IDs and per-stage timings: `retrieval_ms`, `llm_ms`, `tts_first_byte_ms`, `tts_ms`, `stt_ms`.
- **Ending** (decision 041):
  - After `MAX_QUESTIONS` answers, or when the client sends `session.end`, Voice Service sends `interview.completed` to Core API.
  - A disconnect or error (including an STT or TTS failure) sends `interview.interrupted` with an `error_message`.

## Protocol v2

```
Client → Server   session.start {token} · <binary PCM16 16 kHz> · audio.end {}
                  answer.text {text} (typed fallback) · session.end {}
Server → Client   session.ready {interview_id} · question.text {turn_id, seq, text}
                  <binary PCM16 24 kHz> · question.audio_end {turn_id}
                  transcript.final {turn_id, text} · turn.complete {turn_id}
                  session.end {reason} · error {code, message}
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
  speech/stt.py           PCM → MP3, Groq Whisper transcription
  speech/tts.py           Deepgram Aura-2, streamed PCM
sql/schema.sql            turns DDL, applied at startup
scripts/interview_cli.py  terminal client: mic in, speakers out
```

## Running locally

Prerequisites: Postgres (`docker compose up -d` from the repo root), with Core API and Repository Service running.

```bash
uv sync
cp .env.example .env        # fill in GROQ_API_KEY, DEEPGRAM_API_KEY and INTERNAL_HMAC_SECRET
uv run uvicorn voice_service.main:app --reload --port 8002
```

To try an interview:

1. Log in to Core API.
2. `POST /v1/interviews` with a `ready` repository and copy the `session_token`. It expires after 5 minutes.
3. Run:

```bash
uv run python scripts/interview_cli.py <session_token>
```

Each question prints and plays through your speakers. When it finishes, press Enter to start recording and Enter again to send. Type `/t <answer>` to answer by typing, or `/end` to stop early.

## Tests

```bash
uv run pytest
```

The runner tests drive the whole loop with fake collaborators: no network, database, LLM, STT or TTS.

## Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql://...` (asyncpg scheme) |
| `CORE_API_BASE_URL` | e.g. `http://127.0.0.1:8000` |
| `REPOSITORY_SERVICE_BASE_URL` | e.g. `http://127.0.0.1:8001` |
| `INTERNAL_HMAC_SECRET` | Must match the other services (decision 027) |
| `GROQ_API_KEY` | Free key from console.groq.com |
| `LLM_MODEL` | litellm model string, default `groq/qwen/qwen3.8-27b` |
| `STT_MODEL` | litellm transcription model, default `groq/whisper-large-v3-turbo` |
| `DEEPGRAM_API_KEY` | Deepgram key for TTS (new accounts get $200 credit) |
| `TTS_VOICE` | Deepgram voice, default `aura-2-thalia-en` |
| `MAX_ANSWER_SECONDS` | Longest accepted spoken answer, default 180 |
| `MAX_QUESTIONS` | Questions per interview, default 6 |
| `SESSION_START_TIMEOUT_S` | Wait for `session.start`, default 10 |
| `RETRIEVAL_TOP_K` | Chunks per question, default 6 |

## What's next

- **Measure the turn latency** against the 4–5 s target (decision 006) using `turns.timings`.
