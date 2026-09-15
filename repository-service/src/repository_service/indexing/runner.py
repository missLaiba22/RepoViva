"""Entry point for running one indexing pass end-to-end."""

from pathlib import Path

import asyncpg

from repository_service.indexing.app import build_app


async def run_indexing(
    *,
    repository_id: str,
    commit_sha: str,
    source_dir: Path,
    pool: asyncpg.Pool,
) -> None:
    """Build the per-repo CocoIndex app and run one update pass."""
    app = build_app(
        repository_id=repository_id,
        commit_sha=commit_sha,
        source_dir=source_dir,
        pool=pool,
    )
    await app.update()
