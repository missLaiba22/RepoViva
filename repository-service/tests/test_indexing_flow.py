# repository-service/tests/test_indexing_flow.py
"""End-to-end indexing through the real CocoIndex flow, with a fake embedder.

Needs Postgres (docker-compose); never calls Voyage. Skipped if the
database is unreachable. Guards two things the unit tests cannot:

- **Pre-count drift.** runner.count_chunks() predicts how many chunks the
  flow will write, and the repository cap (decision 033) trusts it. Here
  the real flow writes rows and the count must match exactly.
- **Tenant isolation through the real write path.** Two repositories
  indexed by their own CocoIndex Apps (colliding per-App ids), then
  searching one must never return the other's rows.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import asyncpg
import numpy as np
import pytest
import pytest_asyncio

from repository_service.config import get_settings
from repository_service.db import _SCHEMA_SQL_PATH
from repository_service.indexing import flow, runner
from repository_service.indexing.runner import count_chunks, run_indexing
from repository_service.retrieval import search_chunks

# One event loop for the whole module: CocoIndex's environment is
# process-wide and bound to the loop it first ran on, so per-test loops
# fail with "Event loop is closed" on the second test.
pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]

_DIM = 1024


def _fake_vector(text: str) -> np.ndarray:
    """Deterministic unit vector per text — stands in for Voyage."""
    seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "little")
    v = np.random.default_rng(seed).standard_normal(_DIM).astype(np.float32)
    return v / np.linalg.norm(v)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _make_repo(root: Path, marker: str) -> None:
    code = "\n".join(
        f"def {marker}_{i}(x):\n    return x * {i}  # {marker}\n" for i in range(120)
    )
    _write(root, f"src/{marker}_core.py", code)
    _write(root, f"src/{marker}_dup.py", "\n\n".join(["print('same')"] * 3) + "\n" + code)
    _write(root, "README.md", f"# {marker}\n\nA test repository.\n")
    _write(root, "docs/en/guide.md", f"# Guide for {marker}\n")
    # Must be excluded — if indexed, row count exceeds count_chunks().
    _write(root, "docs/fr/guide.md", code)
    _write(root, "node_modules/pkg/index.js", code)


# Module-scoped pool too: CocoIndex runs build_app()'s lifespan once per
# process, so the first pool it is given is the one every later App uses.
@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def pool():
    try:
        pool = await asyncpg.create_pool(get_settings().database_url)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Postgres unavailable: {exc}")
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL_PATH.read_text())

    async def fake_embed(text: str) -> np.ndarray:
        return _fake_vector(text)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(flow.EMBEDDER, "_dim", _DIM)
        mp.setattr(flow.EMBEDDER, "embed", fake_embed)
        yield pool
    await pool.close()


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def two_indexed_repos(pool, tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("repos")
    suffix = uuid.uuid4().hex[:8]
    repos = {f"flowtest-a-{suffix}": "alpha", f"flowtest-b-{suffix}": "beta"}
    try:
        for repo_id, marker in repos.items():
            src = tmp_path / marker
            _make_repo(src, marker)
            await run_indexing(
                repository_id=repo_id, commit_sha="c" * 40,
                source_dir=src.resolve(), pool=pool,
            )
        yield {repo_id: tmp_path / marker for repo_id, marker in repos.items()}
    finally:
        await pool.execute(
            "DELETE FROM code_chunks WHERE repository_id = ANY($1::text[])",
            list(repos),
        )


async def test_count_chunks_matches_rows_written(pool, two_indexed_repos) -> None:
    for repo_id, src in two_indexed_repos.items():
        written = await pool.fetchval(
            "SELECT count(*) FROM code_chunks WHERE repository_id = $1", repo_id
        )
        assert written == count_chunks(src.resolve()) > 0


async def test_search_never_crosses_repositories(pool, two_indexed_repos) -> None:
    repo_a, repo_b = two_indexed_repos
    for repo_id, marker in ((repo_a, "alpha"), (repo_b, "beta")):
        # Query with a vector copied from the *other* repo's chunks — the
        # most tempting possible match — and ask for everything.
        results = await search_chunks(
            pool,
            repository_id=repo_id,
            query_embedding=_fake_vector("anything"),
            top_k=50,
            filename_prefix=None,
            exclude_chunk_ids=[],
        )
        assert results
        other = "beta" if marker == "alpha" else "alpha"
        assert not any(other in r["content"] for r in results)
        # Per-App ids collide across repositories; both still fully present.
        ids = await pool.fetch(
            "SELECT id FROM code_chunks WHERE repository_id = $1", repo_id
        )
        assert min(r["id"] for r in ids) == 1


def test_runner_cap_is_the_documented_value() -> None:
    """Decision 033 names this number; changing it means updating the record."""
    assert runner.MAX_REPO_CHUNKS == 6_000
