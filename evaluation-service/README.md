# Evaluation Service

Turns a finished interview into a report. Each answer gets a correctness and a clarity score (1–5) against the code its question was generated from, plus key points citing the repository's files (decisions 049–051).

## What's implemented

- **Trigger.** Core API sends `POST /internal/v1/reports` when an interview ends. It always gets a 202. A new or `failed` report is claimed as `generating` and built in the background. One that is already `generating` or `ready` is left alone, so a repeated trigger is a no-op (decision 049).
- **Inputs over HTTP**, never from other services' tables (decision 021):
  - the turns from Voice Service (`GET /internal/v1/interviews/{id}/turns`)
  - the exact code chunks behind each question from Repository Service (`POST /internal/v1/repositories/{id}/chunks`), fetched in one batched call
- **Grading** (decision 050):
  - Each answered turn is graded in its own call to Groq `gpt-oss-120b`, with the question, the answer, the previous exchange and that turn's chunks. Turns are graded one at a time, because the per-minute token limit is the bottleneck (decision 051).
  - The model returns JSON: correctness and clarity (1–5, each with a justification), strengths, gaps, 2–4 key points citing chunk ids, and evidence chunk ids.
- **Grounding checks in code:**
  - Citations of chunks the model wasn't shown are dropped.
  - Key points with no valid citation left are dropped.
  - "chunk 142" in the prose is rewritten to `file:line`.
  - Invalid JSON gets one retry, then the turn is `not_graded`.
- **Summary.** Averages are computed in code. One more LLM call writes strengths, areas to improve and files to revisit (only files behind a graded turn).
- **Partial interviews** (decision 008): an `interrupted` outcome gives `partial: true`. Unanswered turns are listed as `not_answered` and not scored.
- **Recovery:**
  - On startup, every report still `generating` (from a crash or reload) is resumed, oldest first.
  - A failure (Voice, Repository or Groq down, or the daily token limit spent) marks the report `failed` with a short error. The next trigger regenerates it.
  - Core API re-sends the trigger if it reads a report that doesn't exist yet.

A six-turn report takes 50–90 s and about 18k tokens.

## Endpoints

Both are internal, HMAC-signed (decision 027), and called only by Core API.

| Endpoint | Response |
|---|---|
| `POST /internal/v1/reports` `{interview_id, repository_id, outcome}` | 202 `{interview_id, status, scheduled}`; `outcome` is `completed` or `interrupted` |
| `GET /internal/v1/reports/{interview_id}` | The report in its current state (content fields null while `generating`), 404 if none |
| `GET /health` | No auth |

Report states: `generating` → `ready` or `failed`. The frontend reads reports through Core API's `GET /v1/interviews/{id}/report`.

## Layout

```
src/evaluation_service/
  internal/router.py      POST/GET /internal/v1/reports
  internal/hmac_auth.py   sign + verify (decision 027)
  generation.py           background run: pipeline → ready/failed; startup resume
  pipeline.py             turns → chunks → grade each turn → summary
  reports.py              reports persistence; each status change is one SQL statement
  clients/voice.py        turns (HMAC)
  clients/repository.py   chunks by id (HMAC)
  grading/prompts.py      grading and summary prompts, PROMPT_VERSION
  grading/llm.py          JSON calls via litellm, retry, 429 waits, token count
  grading/grader.py       one turn's grade + citation checks
  grading/summary.py      averages + written summary
sql/schema.sql            reports DDL, applied at startup
scripts/eval_report.py    print one interview's report without storing it
evals/                    grader sanity sets, harness and results
```

## Running locally

Prerequisites: Postgres (`docker compose up -d` from the repo root), with Voice Service and Repository Service running.

```bash
uv sync
cp .env.example .env        # fill in GROQ_API_KEY and INTERNAL_HMAC_SECRET
uv run uvicorn evaluation_service.main:app --port 8003
```

No `--reload`: a reload stops a report mid-generation. It resumes on the next start, but that costs the tokens again.

To read one interview's report without storing it:

```bash
uv run python scripts/eval_report.py <interview_id> <repository_id> [--partial]
```

## Tests

```bash
uv run pytest
```

Unit tests use a fake LLM and in-memory stores, so they say nothing about grading quality. That's what the sanity sets in [`evals/`](evals/) are for: real questions with strong, vague and wrong answers, graded by the real model.

## Grading quality

Prompt v5 is in use. Sanity set v1 passes 24/24 checks over 3 runs. Set v2 passes 14/16, with two known limitations (decision 050):

- **Code outside the excerpts is under-scored.** A correct, concrete answer about code the question's chunks don't show can get 2/5.
- **A score can contradict its own gap.** An answer whose gap calls its core claim inaccurate can still get 3/5.

A prompt fix for both (v6) had no effect and was reverted.

## Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql://...` (asyncpg scheme) |
| `VOICE_SERVICE_BASE_URL` | e.g. `http://127.0.0.1:8002` |
| `REPOSITORY_SERVICE_BASE_URL` | e.g. `http://127.0.0.1:8001` |
| `INTERNAL_HMAC_SECRET` | Must match the other services (decision 027) |
| `GROQ_API_KEY` | Free key from console.groq.com |
| `EVAL_LLM_MODEL` | litellm model string, default `groq/openai/gpt-oss-120b` |

On Windows, use `127.0.0.1`, not `localhost`: `localhost` adds about 2 s per call.

## Limits

- Groq's free tier allows 200,000 tokens per rolling 24 h for the grading model: about 10 reports a day (decision 051). Once it's spent, reports end `failed` until a new trigger.
- One report at a time.
- A `failed` report isn't regenerated when it's read. Today it needs a new trigger.
