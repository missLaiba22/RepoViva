# Evaluation Service

Turns a finished interview into a report: each answer gets a correctness and a clarity score (1–5) against the code its question came from, plus key points citing the repository's files (decisions 049–051). How it fits in: [docs/architecture.md](../docs/architecture.md).

## Responsibilities

- **Trigger:** the worker generates a report on `interview.ended`, or on a `report.requested` job from Core API (recovery and retry). It runs unless the report is already `ready`; one left `generating` by a crash reruns.
- **Inputs over HTTP**, never other services' tables: turns from Voice Service, the exact code chunks behind each question from Repository Service.
- **Grading** (decision 050): each answered turn is graded in its own call to Groq `gpt-oss-120b`, one at a time to stay within the token limit. The model returns scores with justifications, strengths, gaps and 2–4 cited key points.
- **Grounding checks in code:** citations of chunks the model wasn't shown are dropped, as are key points left without one; "chunk 142" becomes `file:line`; invalid JSON gets one retry, then the turn is `not_graded`.
- **Summary:** averages computed in code, plus one LLM call for strengths, areas to improve and files to revisit.
- **Partial interviews:** an `interrupted` interview gives `partial: true`; unanswered turns are `not_answered` (decision 008).

A six-turn report takes 50–90 s and about 18k tokens. States: `generating → ready | failed`.

## API

| Endpoint | Notes |
|---|---|
| `GET /internal/v1/reports/{interview_id}` | HMAC, called by Core API. The report in its current state; 404 if none |
| `GET /health` | Liveness |

## Messaging

| | Queue | Message |
|---|---|---|
| Consumes | `evaluation-interview-events` | `interview.ended` |
| Consumes | `report-jobs` | `report.requested` |

## Run locally

Needs Postgres and LocalStack (`docker compose up -d`), with Voice Service and Repository Service running.

```bash
uv sync
cp .env.example .env
uv run uvicorn evaluation_service.main:app --port 8003
uv run python -m evaluation_service.worker
```

Print one interview's report without storing it: `uv run python scripts/eval_report.py <interview_id> <repository_id> [--partial]`.

## Configuration

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Plain `postgresql://...` (asyncpg) |
| `VOICE_SERVICE_BASE_URL`, `REPOSITORY_SERVICE_BASE_URL` | Turns and chunks |
| `INTERNAL_HMAC_SECRET` | Same value in every service |
| `GROQ_API_KEY` | Grading |
| `EVAL_LLM_MODEL` | Default `groq/openai/gpt-oss-120b` |
| `AWS_*`, `INTERVIEW_EVENTS_QUEUE_URL`, `REPORT_JOBS_QUEUE_URL` | SQS; see `.env.example` |

## Tests and grading quality

```bash
uv run ruff check . && uv run pytest
```

Unit tests use a fake LLM, so they say nothing about grading quality. The sanity sets in [`evals/`](evals/) do: real questions with strong, vague and wrong answers, graded by the real model. Prompt v5 passes set v1 24/24 and set v2 14/16; the two known misses are under-scoring correct answers about code outside the excerpts, and a score that can contradict its own gap (decision 050).

## Limits

- Groq's free tier allows 200k tokens per rolling 24 h for the grading model: about 10 reports a day. After that, reports end `failed` until retried.
- One report at a time.
