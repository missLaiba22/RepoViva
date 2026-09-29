-- Repository Service schema, applied by repository_service.db.apply_schema().
--
-- code_chunks is shared by every repository's CocoIndex indexing App (see
-- indexing/app.py — one App per repository_id). Ownership of this table's
-- DDL therefore cannot live inside the per-repo CocoIndex flow: a fresh App
-- has no record of a table a *different* App already created, and would
-- issue a plain CREATE TABLE that fails with DuplicateTableError against a
-- table that already exists. So this file — not CocoIndex — owns the DDL,
-- and indexing/flow.py mounts the table with managed_by=ManagedBy.USER,
-- meaning CocoIndex only reconciles rows against it, never table structure.
--
-- Column types are copied to match exactly what
-- cocoindex.connectors.postgres.TableSchema.from_class(CodeChunk, ...)
-- would generate, so CocoIndex's own row encoding stays compatible with a
-- table it didn't create. Keep this in sync with indexing/schema.py's
-- CodeChunk dataclass if it changes.
--
-- PRIMARY KEY is (repository_id, id) rather than bare id: `id` comes from
-- CocoIndex's IdGenerator, a sequential counter scoped per App (starts
-- at 1 every time) — not globally unique. With one App per repository_id,
-- two repositories' first chunk both land on id=1; a bare-id primary key
-- would let the second repository's row silently overwrite the first's
-- via ON CONFLICT (id) DO UPDATE. See indexing/flow.py's app_main().

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS code_chunks (
    id BIGINT NOT NULL,
    repository_id TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    filename TEXT NOT NULL,
    start_line BIGINT NOT NULL,
    end_line BIGINT NOT NULL,
    language TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1024) NOT NULL,
    PRIMARY KEY (repository_id, id)
);

-- No ANN (ivfflat/hnsw) index on `embedding` — retrieval is exact
-- nearest-neighbour search, scoped by the primary key's leading
-- repository_id column (decision 033). No separate B-tree on
-- repository_id is needed: PRIMARY KEY (repository_id, id) already is one.
--
-- Earlier versions created an ivfflat index here at startup, on an empty
-- table, so its k-means lists were never trained on real data. Drop it
-- from existing databases so they get exact search too.
DROP INDEX IF EXISTS "code_chunks__vector__embedding";
