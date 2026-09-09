# Repository Service

RepoViva's Repository Service. Owns repository ingestion (fetching, parsing, chunking, embedding) and retrieval. This is the second of the four microservices — see `docs/architecture.md` for the full picture.

## Current status

**Slice 2 (in progress).** The service currently accepts an ingest trigger from Core API and runs a stubbed background job that simulates progress by firing status-callback events back to Core API. Real repository fetching, parsing, chunking, and embedding are not implemented yet — they land in a later slice.

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

See `docs/architecture.md` and `docs/decisions.md` for the shape of real ingestion. The next slice replaces the stubbed background job with real repository fetching from GitHub, code parsing, and pgvector-backed embedding storage.