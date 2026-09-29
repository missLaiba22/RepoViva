"""Entry point for running one indexing pass end-to-end."""

import asyncio
import os
from pathlib import Path, PurePosixPath
from typing import Final

import asyncpg

from repository_service.indexing.app import build_app
from repository_service.indexing.flow import PATH_MATCHER, split_source

# Largest repository we index, in chunks (decision 033). Retrieval is exact
# nearest-neighbour search whose cost is linear in one repository's chunk
# count (~12 µs/chunk measured); ~6,000 chunks is where p95 reaches the
# 100 ms retrieval budget.
MAX_REPO_CHUNKS: Final = 6_000


class RepositoryTooLargeError(Exception):
    def __init__(self, chunk_count: int, limit: int) -> None:
        self.chunk_count = chunk_count
        self.limit = limit
        super().__init__(
            f"repository too large: {chunk_count:,} chunks (limit {limit:,})"
        )


def count_chunks(source_dir: Path) -> int:
    """Count the chunks indexing would produce, without embedding anything.

    Walks with the flow's own PATH_MATCHER and splits with its own
    split_source(), so the count matches what index_file() would embed.
    """
    total = 0
    for dirpath, dirnames, filenames in os.walk(source_dir):
        rel_dir = PurePosixPath(Path(dirpath).relative_to(source_dir).as_posix())
        # Prune excluded directories (node_modules, .git, translations, ...)
        # in place so os.walk never descends into them.
        dirnames[:] = [
            d for d in dirnames if PATH_MATCHER.is_dir_included(rel_dir / d)
        ]
        for name in filenames:
            rel = rel_dir / name
            if not PATH_MATCHER.is_file_included(rel):
                continue
            source = (Path(dirpath) / name).read_bytes().decode(
                "utf-8-sig", errors="replace"
            )
            total += len(split_source(rel.as_posix(), source)[1])
    return total


async def run_indexing(
    *,
    repository_id: str,
    commit_sha: str,
    source_dir: Path,
    pool: asyncpg.Pool,
) -> None:
    """Build the per-repo CocoIndex app and run one update pass.

    Raises RepositoryTooLargeError — before any embedding call — if the
    repository would exceed MAX_REPO_CHUNKS.
    """
    # Splitting is CPU-bound; keep it off the event loop.
    chunk_count = await asyncio.to_thread(count_chunks, source_dir)
    if chunk_count > MAX_REPO_CHUNKS:
        raise RepositoryTooLargeError(chunk_count, MAX_REPO_CHUNKS)

    app = build_app(
        repository_id=repository_id,
        commit_sha=commit_sha,
        source_dir=source_dir,
        pool=pool,
    )
    await app.update()
