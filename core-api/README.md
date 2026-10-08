# Core API

RepoViva's main REST entry point for the frontend. Owns GitHub OAuth and sessions, users, repository metadata and ingestion status, and interviews. See [docs/architecture.md](../docs/architecture.md) for how it fits with the other services.

## What's implemented

- **Auth** — GitHub OAuth with a signed state cookie; session kept in a signed `repoviva_session` cookie. OAuth tokens are encrypted at rest (decision 005).
- **Repositories** — submit a GitHub URL, which creates a `queued` row and triggers ingestion on Repository Service (HMAC-signed). Status moves `queued → in_progress → ready | failed` as Repository Service reports back (decision 029).
- **Interviews** — create an interview for a `ready` repository and receive a single-use session token. Only its hash is stored; the raw token is returned once (decisions 035–036). You can list your interviews or fetch one, and the responses never include a token.
- **Interview lifecycle events** — Voice Service reports the end of a session. Only an `active` interview can move to `completed` or `interrupted` (decision 036).
- **Session token consumption** — Voice Service exchanges a session token once for `{ interview_id, user_id, repository_id }`. One atomic `UPDATE` burns the token and moves the interview `created → active`. A token that is rejected gets a 403 with `reason` set to `unknown`, `expired` or `consumed` (decisions 035–036).
- **Internal callback** — receives HMAC-signed ingestion events from Repository Service.

All user-facing queries are scoped to the current user.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/auth/github/login` | Redirects to GitHub |
| GET | `/v1/auth/github/callback` | Sets the session cookie |
| GET | `/v1/me` | Current user |
| POST | `/v1/repositories` | `{ github_url }` |
| GET | `/v1/repositories` | List your repositories |
| GET | `/v1/repositories/{id}` | Includes ingestion status |
| POST | `/v1/interviews` | `{ repository_id }` → interview + session token. 404 if not yours, 409 if not `ready` |
| GET | `/v1/interviews` | List your interviews, newest first |
| GET | `/v1/interviews/{id}` | One interview. 404 if missing or not yours |
| POST | `/internal/v1/repositories/{id}/events` | Ingestion callbacks (HMAC) |
| POST | `/internal/v1/interviews/{id}/events` | `interview.completed` / `interview.interrupted` from Voice Service. 404 unknown, 422 if not `active` (HMAC) |
| POST | `/internal/v1/session-tokens/consume` | `{ token }` → `{ interview_id, user_id, repository_id }`. 403 `{ reason }` if unknown, expired or consumed (HMAC) |
| GET | `/health`, `/health/db` | Liveness / DB check |

## Running locally

Prerequisites: Python 3.11+, `uv`, Postgres running (`docker compose up -d` from the repo root).

```bash
uv sync
cp .env.example .env        # then fill in the values below
uv run alembic upgrade head
uv run uvicorn core_api.main:app --reload --port 8000
```

Log in by opening `http://localhost:8000/v1/auth/github/login` in a browser.

## Tests

```bash
uv run pytest
```

## Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://...` |
| `ENV` | `development` or `production` |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | From your GitHub OAuth app |
| `GITHUB_OAUTH_REDIRECT_URI` | `http://localhost:8000/v1/auth/github/callback` locally |
| `COOKIE_SECRET` | Signs state and session cookies |
| `TOKEN_ENCRYPTION_KEY` | Encrypts stored GitHub tokens |
| `REPOSITORY_SERVICE_BASE_URL` | e.g. `http://127.0.0.1:8001` |
| `EVALUATION_SERVICE_BASE_URL` | Report trigger and report reads, e.g. `http://127.0.0.1:8003` |
| `INTERNAL_HMAC_SECRET` | Must match Repository Service's (decision 027) |
| `SESSION_TOKEN_TTL_MINUTES` | Interview token lifetime if unused (default 5) |

Generate secrets with `python -c "import secrets; print(secrets.token_hex(32))"`.

## Migrations

Alembic manages only Core API's tables (decision 037):

```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

## What's next

`GET /v1/interviews/{id}/report` once Evaluation Service exists, and a fix for interviews stuck in `active` if Voice Service crashes (decision 036's revisit trigger).
