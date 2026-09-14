# Repository Service

RepoViva's Repository Service. Owns repository ingestion (fetching, parsing, chunking, embedding) and retrieval. This is the second of the four microservices — see `docs/architecture.md` for the full picture.



## Current status

**Slice 3, step 1 complete.** The service:

- Accepts an HMAC-signed ingest trigger from Core API.
- Shallow-clones the repository into an ephemeral workspace
  (`workspace/<repository_id>/`, see decision on workspace layout).
- Reports status back to Core API as HMAC-signed HTTP callbacks
  (`ingestion.started`, `ingestion.completed`, `ingestion.failed`) —
  see decisions 024–026 and 029.
- Surfaces real git errors as `error_message` on the failed row so
  the frontend can display them.

The parse → chunk → embed → index stages are not yet implemented.
The pipeline currently ends immediately after the clone succeeds
(or emits `ingestion.failed` on any exception during the clone).

## Running locally

Prerequisites: Python 3.11+, `uv`.

```bash
# From this directory
uv sync
cp .env.example .env
# Edit .env — generate INTERNAL_HMAC_SECRET and match it to core-api/.env

# Start the service on :8001 (core-api uses :8000)
uv run uvicorn repository_service.main:app --reload --port 8001
```

Health check:

```bash
curl http://localhost:8001/health
```

## Running tests

```bash
uv run pytest
```

## Environment variables

| Variable                | Purpose                                                              |
|-------------------------|----------------------------------------------------------------------|
| `ENV`                   | `development` or `production`                                        |
| `CORE_API_BASE_URL`     | Base URL for Core API — used when firing status callbacks            |
| `INTERNAL_HMAC_SECRET`  | Shared secret for HMAC signing on internal calls (see decision 027). Must match `core-api/.env`. |

## What's next
## What's next

Real parse/chunk/embed via CocoIndex, storing chunks + embeddings
in pgvector — see `docs/architecture.md`. That work slots into
`ingestion/orchestrator.py` between the fetch-complete log line
and the `ingestion.completed` callback.