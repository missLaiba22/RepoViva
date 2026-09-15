"""FastAPI-owned asyncpg pool for Repository Service.

The pool is opened in main.py's lifespan and closed on shutdown.
Background tasks (e.g. the ingestion orchestrator) call get_db_pool()
to reuse the same pool — Depends() is not available outside request
scope.
"""

from __future__ import annotations

from pathlib import Path

import asyncpg

from repository_service.config import get_settings

_pool: asyncpg.Pool | None = None

_SCHEMA_SQL_PATH = Path(__file__).resolve().parent.parent.parent / "sql" / "schema.sql"


async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(get_settings().database_url)


async def apply_schema() -> None:
    """Apply sql/schema.sql idempotently against the pool.

    Owns the code_chunks table's DDL so that CocoIndex's per-repository
    indexing Apps (indexing/app.py) never issue CREATE TABLE themselves —
    see sql/schema.sql for why that matters across multiple repositories.
    """
    sql = _SCHEMA_SQL_PATH.read_text()
    async with get_db_pool().acquire() as conn:
        await conn.execute(sql)


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_db_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized — check FastAPI lifespan")
    return _pool