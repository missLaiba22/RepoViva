# RepoViva — engineering rules

Services: core-api, repository-service, voice-service, evaluation-service (Python 3.11, FastAPI); frontend (React/Vite).
Source of truth: `docs/architecture.md` (current design) and `docs/decisions.md` (why). Read both before changing service boundaries, internal contracts, or how services communicate.

## Decisions
- Never change the design silently. Propose the decision (context, options, choice) and stop for approval. Only after approval, add it to `docs/decisions.md` and implement it.

## Commands
<!-- TODO: replace <...> with real paths and ports, then delete this comment. -->
- Run a service: `cd <services-dir>/<service> && uvicorn main:app --host 127.0.0.1 --port <port>`
- Check a service: `cd <services-dir>/<service> && ruff check . && pytest`
- Frontend: `cd frontend && npm run dev` · check: `npm run lint && npm test`
- Ports: core-api <port> · repository-service <port> · voice-service <port> · evaluation-service <port> · frontend <port>

## Service boundaries
- One service, one responsibility. Logic goes in the service that owns it.
- A service owns its data. Never read or write another service's tables or collections; call its API.
- Services deploy and run independently: no shared domain models, no shared DB code.
- Shared package `repoviva-common` at `libs/repoviva-common` (decision 054) holds infrastructure only: HMAC, HTTP client factory, logging, request-ID middleware. Never domain models, DB code, or business logic. Import from it; never copy its code into a service.

## Communication
- Sync: REST over HTTP/JSON under `/internal/...`, authenticated with HMAC (decision 027).
- Request/response bodies are Pydantic models. Changing an internal contract needs a decision first.
- Forward `X-Request-ID` on every outbound call and include it in every log line.
- Background work (ingestion, question planning, report generation) currently runs via FastAPI `BackgroundTasks`. Do not add a message queue without a decision.
- Jobs are plain functions that take only an id and load everything else from the DB (e.g. `evaluation_service/generation.py:run_generation`), so they can move to a queue unchanged.

## Resilience
- Make outbound HTTP calls only through the service's single `httpx.AsyncClient`, created at startup from the shared factory (which sets the timeout). No ad-hoc clients.
- Retry only idempotent calls, with backoff.
- Jobs are idempotent: check the stored status first so a rerun does nothing. Job state lives in the DB, never in memory.
- A failing dependency returns a clear error (<TODO: status + body, e.g. 503 {"error", "retryable": true}>), never an unhandled exception.
- Every service exposes `GET /health`.

## Code structure (same in every service)
- `main.py` (app wiring) · `config.py` (settings) · `db.py` (persistence) · `internal/` (routers) · `clients/` (outbound calls) · domain packages (logic).
- Routers only validate, call domain logic, and return. No business logic in routers.
- Config comes from env vars via the settings object. No hard-coded URLs or secrets.
- Type hints everywhere. Comments only for the non-obvious why.

## Testing (kept light on purpose)
- Do not add tests for every change. Write tests only for: internal contract shapes, job idempotency, and regressions for fixed bugs.
- Before committing, run `ruff check` and the existing tests of the service you changed.

## Commits
- Conventional Commits with the service as scope, e.g. `feat(core-api): ...`. keep it to the point

