# Core API

The frontend's only REST API. Owns GitHub login and sessions, users, repositories (with their ingestion status) and interviews. How it fits in: [docs/architecture.md](../docs/architecture.md).

## Responsibilities

- **Auth:** GitHub OAuth; the session lives in a signed cookie, GitHub tokens are encrypted at rest (decision 005).
- **Repositories:** a submitted URL becomes a `queued` row and an ingestion job. Status moves `queued → in_progress → ready | failed` from Repository Service's events; a failed one can be retried in place (decision 061).
- **Interviews:** created for a `ready` repository with a single-use session token (only its hash is stored, decisions 035–036). Voice Service burns the token to start the session.
- **Ending:** `interview.ended` moves an `active` interview to `completed` or `interrupted`. An `active` interview past its cutoff is ended when read, in case that event never arrives (decision 059).
- **Plan and report:** proxies the question plan from Voice Service and the report from Evaluation Service, re-sending their jobs when needed.

All user-facing queries are scoped to the signed-in user.

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/auth/github/login` · `/callback` | GitHub OAuth; sets the session cookie |
| POST | `/v1/auth/github/logout` | Clears the session |
| GET | `/v1/me` | Current user |
| POST | `/v1/repositories` | `{ github_url }` → sends the ingestion job |
| GET | `/v1/repositories` · `/{id}` | List or read, with ingestion status |
| POST | `/v1/repositories/{id}/retry` | Retry a failed ingestion (202) |
| POST | `/v1/interviews` | `{ repository_id }` → interview + session token; sends the plan job. 409 if the repository isn't ready |
| GET | `/v1/interviews` · `/{id}` | List (newest first) or read |
| GET | `/v1/interviews/{id}/plan` | Plan status; 503 if Voice Service is down |
| POST | `/v1/interviews/{id}/plan/retry` | Re-send the plan job; 409 once started |
| GET | `/v1/interviews/{id}/report` | The report; 202 while grading |
| POST | `/v1/interviews/{id}/report/retry` | Regenerate a failed report |
| POST | `/internal/v1/session-tokens/consume` | HMAC. `{ token }` → interview, user, repository; 403 `{ reason }` if rejected |
| GET | `/health` · `/health/db` | Liveness and DB check |

## Messaging

| | Queue | Message |
|---|---|---|
| Sends | `ingestion-jobs` | `ingestion.requested` |
| Sends | `planning-jobs` | `plan.requested` |
| Sends | `report-jobs` | `report.requested` |
| Consumes | `core-ingestion-events` | `ingestion.started` / `completed` / `failed` |
| Consumes | `core-interview-events` | `interview.ended` |

## Run locally

Needs Postgres and LocalStack (`docker compose up -d` from the repo root).

```bash
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn core_api.main:app --reload --port 8000
uv run python -m core_api.worker
```

## Configuration

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://...` |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_OAUTH_REDIRECT_URI` | Your GitHub OAuth app |
| `FRONTEND_BASE_URL` | Where to land after login (default `http://localhost:5173`) |
| `COOKIE_SECRET`, `TOKEN_ENCRYPTION_KEY` | Sign cookies, encrypt GitHub tokens |
| `COOKIE_SECURE` | `true` behind HTTPS (production) |
| `VOICE_SERVICE_BASE_URL`, `EVALUATION_SERVICE_BASE_URL` | Plan and report reads |
| `INTERNAL_HMAC_SECRET` | Same value in every service (decision 027) |
| `AWS_*`, `*_QUEUE_URL` | SQS; see `.env.example` (LocalStack locally) |
| `SESSION_TOKEN_TTL_MINUTES` | Unused token lifetime (default 5) |
| `ACTIVE_SESSION_CUTOFF_SECONDS` | When an `active` interview counts as overdue (default 2100) |

Generate secrets with `python -c "import secrets; print(secrets.token_hex(32))"`.

## Tests and migrations

```bash
uv run ruff check . && uv run pytest
uv run alembic revision --autogenerate -m "describe change"   # Core API's tables only (decision 037)
```
