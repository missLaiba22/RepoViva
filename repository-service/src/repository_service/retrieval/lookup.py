# repository-service/src/repository_service/retrieval/lookup.py
"""Fetch code_chunks by id, for Evaluation Service (decision 049).

Grading needs the exact chunks a question was generated from
(`turns.retrieved_chunk_ids`), not a fresh similarity search.
"""

from __future__ import annotations

import asyncpg

# Chunk ids are only unique per repository (decision 031), so the lookup
# is always scoped by repository_id. The primary key (repository_id, id)
# serves it directly.
_LOOKUP_SQL = """
    SELECT id, content, filename, start_line, end_line, language
    FROM code_chunks
    WHERE repository_id = $1
      AND id = ANY($2::bigint[])
    ORDER BY id
"""


async def get_chunks_by_ids(
    pool: asyncpg.Pool,
    *,
    repository_id: str,
    ids: list[int],
) -> list[dict]:
    """The chunks among `ids` that exist for `repository_id`, ordered by id.

    Ids with no row (re-ingested or unknown repository) are simply absent;
    the caller decides what a missing chunk means.
    """
    rows = await pool.fetch(_LOOKUP_SQL, repository_id, ids)
    return [dict(row) for row in rows]
