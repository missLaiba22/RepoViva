# Repository Service

Ingests GitHub repositories (clone → chunk → embed) and serves retrieval over the indexed code. Called only by other services, never by the frontend. How it fits in: [docs/architecture.md](../docs/architecture.md).

## Responsibilities

- **Ingestion:** the worker shallow-clones the repository, chunks it with CocoIndex's syntax-aware splitter, embeds with Voyage `voyage-4-lite`, and stores the chunks in pgvector. The clone is deleted when ingestion ends.
- **Always finishes:** every job ends `ready` or `failed` (decision 058). A duplicate job does nothing; a failed job restarts when retried (decision 061).
- **Limits:** repositories over 6,000 chunks are rejected before embedding. Translated docs and `i18n/` are skipped (decision 033).
- **Retrieval:** cosine search over a repository's chunks, optionally within a path prefix (decisions 032–033).
- **Areas:** the repository's largest directories for question planning; the largest are split until there are enough (decision 060).

Schema: [sql/schema.sql](sql/schema.sql), applied on startup.

## API

All internal and HMAC-signed (decision 027).

| Method | Path | Notes |
|---|---|---|
| POST | `/internal/v1/repositories/{id}/retrieve` | `{ query, top_k?, filename_prefix? }` → `{ chunks }` |
| POST | `/internal/v1/repositories/{id}/chunks` | `{ ids }` → `{ chunks }` |
| GET | `/internal/v1/repositories/{id}/areas?limit=` | `{ areas }` |
| GET | `/health` | Liveness, no auth |

Unknown or not-yet-indexed repositories return empty lists, not 404.

## Messaging

| | Where | Message |
|---|---|---|
| Consumes | `ingestion-jobs` queue | `ingestion.requested` |
| Publishes | `repoviva` bus | `ingestion.started` / `completed` / `failed` |

## Run locally

Needs Postgres and LocalStack (`docker compose up -d` from the repo root) and a Voyage API key.

```bash
uv sync
cp .env.example .env
uv run uvicorn repository_service.main:app --reload --port 8001
uv run python -m repository_service.worker
```

## Configuration

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Plain `postgresql://...` (asyncpg) |
| `VOYAGE_API_KEY` | Embeddings |
| `WORKSPACE_ROOT` | Scratch space for clones, e.g. `./workspace` |
| `COCOINDEX_DB` | CocoIndex's own state DB |
| `INTERNAL_HMAC_SECRET` | Same value in every service |
| `AWS_*`, `INGESTION_JOBS_QUEUE_URL`, `EVENT_BUS_NAME` | SQS and EventBridge; see `.env.example` |

## Tests

```bash
uv run ruff check .
uv run pytest -m "not integration"   # unit tests
uv run pytest                        # also hits GitHub, Voyage and Postgres
```

Retrieval quality is measured separately: [evals/README.md](evals/README.md).
