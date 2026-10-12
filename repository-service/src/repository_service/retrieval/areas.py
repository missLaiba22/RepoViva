"""A repository's areas, its major parts, for question planning (decision 052).

Areas come only from the directory structure, so they adapt to any
repository and need no LLM call.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import asyncpg

_FILE_COUNTS_SQL = """
    SELECT filename, count(*) AS chunk_count
    FROM code_chunks
    WHERE repository_id = $1
    GROUP BY filename
"""


@dataclass(frozen=True)
class Area:
    # A directory ends with "/", so it works as a retrieval `filename_prefix`
    # without also matching a sibling like "core-api" for "core".
    path: str
    chunk_count: int


def pick_areas(file_counts: dict[str, int]) -> list[Area]:
    """Areas from per-file chunk counts, largest first.

    Start at the root. While there is exactly one directory, step into it
    (the everything-in-`src/` layout). Two or more directories are the
    areas. With none, each file at that level is an area. Files sitting
    next to a single directory are dropped with the step down.
    """
    prefix = ""
    while True:
        dirs: Counter[str] = Counter()
        files: Counter[str] = Counter()
        for filename, count in file_counts.items():
            if not filename.startswith(prefix):
                continue
            head, sep, _ = filename[len(prefix):].partition("/")
            if sep:
                dirs[f"{prefix}{head}/"] += count
            else:
                files[filename] += count

        if len(dirs) == 1:
            (prefix,) = dirs
            continue
        chosen = dirs or files
        areas = [Area(path, count) for path, count in chosen.items()]
        # Path breaks ties so the same repository always gives the same areas.
        return sorted(areas, key=lambda a: (-a.chunk_count, a.path))


async def list_areas(pool: asyncpg.Pool, *, repository_id: str, limit: int) -> list[Area]:
    """The `limit` largest areas; empty if the repository has no chunks."""
    rows = await pool.fetch(_FILE_COUNTS_SQL, repository_id)
    return pick_areas({row["filename"]: row["chunk_count"] for row in rows})[:limit]
