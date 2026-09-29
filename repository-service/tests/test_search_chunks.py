# repository-service/tests/test_search_chunks.py
"""Integration tests for retrieval.search_chunks against a real Postgres.

Rows are inserted directly into code_chunks with synthetic embeddings, so
these tests need Postgres (docker-compose) but never call Voyage. Skipped
if the database is unreachable.
"""

from __future__ import annotations

import uuid

import asyncpg
import numpy as np
import pytest

from repository_service.config import get_settings
from repository_service.db import _SCHEMA_SQL_PATH
from repository_service.retrieval import search_chunks

pytestmark = pytest.mark.integration

_DIM = 1024


def _unit(axis: int) -> np.ndarray:
    """A 1024-dim unit vector pointing along `axis`."""
    v = np.zeros(_DIM, dtype=np.float32)
    v[axis] = 1.0
    return v


def _literal(v: np.ndarray) -> str:
    return "[" + ",".join(str(float(x)) for x in v) + "]"


@pytest.fixture
async def pool():
    try:
        pool = await asyncpg.create_pool(get_settings().database_url)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Postgres unavailable: {exc}")
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL_PATH.read_text())
    yield pool
    await pool.close()


@pytest.fixture
async def two_repos(pool):
    """Seed repo A and repo B with identical ids and overlapping vectors."""
    suffix = uuid.uuid4().hex[:8]
    repo_a, repo_b = f"test-a-{suffix}", f"test-b-{suffix}"
    # Both repos reuse ids 1..3 — mirrors CocoIndex's per-App generate_id().
    rows = [
        (repo, i, f"{repo}/file{i}.py", _literal(_unit(i)))
        for repo in (repo_a, repo_b)
        for i in (1, 2, 3)
    ]
    await pool.executemany(
        """
        INSERT INTO code_chunks (id, repository_id, commit_sha, filename,
            start_line, end_line, language, content, embedding)
        VALUES ($2, $1, 'sha', $3, 1, 1, 'python', $3, $4::vector)
        """,
        rows,
    )
    yield repo_a, repo_b
    await pool.execute(
        "DELETE FROM code_chunks WHERE repository_id = ANY($1::text[])",
        [repo_a, repo_b],
    )


async def test_search_only_returns_requested_repository(pool, two_repos) -> None:
    repo_a, _ = two_repos

    results = await search_chunks(
        pool,
        repository_id=repo_a,
        query_embedding=_unit(2),
        top_k=10,
        filename_prefix=None,
        exclude_chunk_ids=[],
    )

    assert len(results) == 3
    assert all(r["filename"].startswith(f"{repo_a}/") for r in results)


async def test_search_is_exact_nearest_first(pool, two_repos) -> None:
    repo_a, _ = two_repos

    results = await search_chunks(
        pool,
        repository_id=repo_a,
        query_embedding=_unit(2),
        top_k=1,
        filename_prefix=None,
        exclude_chunk_ids=[],
    )

    assert [r["id"] for r in results] == [2]
    assert results[0]["similarity"] == pytest.approx(1.0)


async def test_no_ann_index_on_embedding(pool) -> None:
    """Guards decision 033: nothing (schema.sql or CocoIndex) re-adds one."""
    indexes = await pool.fetch(
        "SELECT indexdef FROM pg_indexes WHERE tablename = 'code_chunks'"
    )
    defs = " ".join(r["indexdef"].lower() for r in indexes)
    assert "ivfflat" not in defs
    assert "hnsw" not in defs
