# repository-service/src/repository_service/retrieval/search.py
"""Similarity search over code_chunks.

Raw SQL rather than a vector-store library (LangChain, etc.) — the query is
one ORDER BY, and code_chunks' schema is owned by this service (decision
031), not by a generic vectorstore wrapper.
"""

from __future__ import annotations

import asyncpg
import numpy as np
from numpy.typing import NDArray

# No pgvector codec is registered on the shared asyncpg pool (db.py), so the
# embedding is sent as a string literal and cast to `vector` in SQL rather
# than bound as a native array/numpy value.
_SEARCH_SQL = """
    SELECT id, content, filename, start_line, end_line, language,
           1 - (embedding <=> $1::vector) AS similarity
    FROM code_chunks
    WHERE repository_id = $2
      AND ($3::text IS NULL OR starts_with(filename, $3))
      AND NOT (id = ANY($4::bigint[]))
    ORDER BY embedding <=> $1::vector
    LIMIT $5
"""


def _to_vector_literal(embedding: NDArray[np.float32]) -> str:
    return "[" + ",".join(str(float(x)) for x in embedding) + "]"


async def search_chunks(
    pool: asyncpg.Pool,
    *,
    repository_id: str,
    query_embedding: NDArray[np.float32],
    top_k: int,
    filename_prefix: str | None,
    exclude_chunk_ids: list[int],
) -> list[dict]:
    """Top-`top_k` chunks for `repository_id`, nearest first.

    Returns an empty list if the repository has no chunks (unknown repo,
    ingestion not yet started/finished) — this endpoint does not
    distinguish those cases; see decision on 404/409 handling.
    """
    rows = await pool.fetch(
        _SEARCH_SQL,
        _to_vector_literal(query_embedding),
        repository_id,
        filename_prefix,
        exclude_chunk_ids,
        top_k,
    )
    return [dict(row) for row in rows]
