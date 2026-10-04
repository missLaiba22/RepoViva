# Repository Service

RepoViva's Repository Service. Ingests GitHub repositories (clone → chunk → embed) and serves retrieval over the indexed code. Called only by other services, never by the frontend. See [docs/architecture.md](../docs/architecture.md) for the full picture.

## What's implemented

- **Ingestion** — on an HMAC-signed trigger from Core API, runs in the background: shallow-clones into `workspace/<repository_id>/`, chunks with CocoIndex's syntax-aware splitter, embeds with Voyage `voyage-4-lite`, and writes rows to the `code_chunks` table (pgvector). Progress is reported to Core API as `ingestion.started` / `completed` / `failed` callbacks (decisions 029–031).
- **Limits** — repositories over 6,000 chunks are rejected before any embedding is done. Translated docs and `i18n/` directories are skipped (decision 033).
- **Retrieval** — exact cosine-distance search over a repository's chunks, with optional filename prefix and chunk exclusion (decisions 032–033).

`code_chunks`' schema lives in [sql/schema.sql](sql/schema.sql) and is applied on startup.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| POST | `/internal/v1/repositories/{id}/ingest` | `{ github_url }` → 202 |
| POST | `/internal/v1/repositories/{id}/retrieve` | `{ query, top_k?, filename_prefix?, exclude_chunk_ids? }` → `{ chunks }` |
| GET | `/health` | Liveness |

Internal endpoints require HMAC headers (decision 027). Retrieval returns an empty list rather than 404 for unknown or not-yet-indexed repositories.

## Running locally

Prerequisites: Python 3.11+, `uv`, Git, Postgres running (`docker compose up -d` from the repo root), a Voyage AI API key.

```bash
uv sync
cp .env.example .env        # then fill in the values below
uv run uvicorn repository_service.main:app --reload --port 8001
```

## Tests

```bash
uv run pytest -m "not integration"   # unit tests only
uv run pytest                        # everything, incl. tests that hit GitHub / Voyage / Postgres
```

Retrieval quality is measured separately. See [evals/README.md](evals/README.md).

## Environment variables

| Variable | Purpose |
|---|---|
| `ENV` | `development` or `production` |
| `CORE_API_BASE_URL` | Where status callbacks are sent, e.g. `http://localhost:8000` |
| `INTERNAL_HMAC_SECRET` | Must match Core API's |
| `DATABASE_URL` | Plain `postgresql://...` (asyncpg doesn't accept `+psycopg`) |
| `VOYAGE_API_KEY` | Embeddings |
| `WORKSPACE_ROOT` | Where clones are stored, e.g. `./workspace` |

## What's next

Callback retries/deduplication and a re-ingestion path are deferred (decision 029).
