"""FastAPI-owned asyncpg pool for Voice Service.

Opened in main.py's lifespan and closed on shutdown. The WebSocket
handler reaches it through get_db_pool() — same shape as
repository_service/db.py.
"""

from __future__ import annotations

from pathlib import Path

import asyncpg

from voice_service.config import get_settings

_pool: asyncpg.Pool | None = None

_SCHEMA_SQL_PATH = Path(__file__).resolve().parent.parent.parent / "sql" / "schema.sql"


async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(get_settings().database_url)


async def apply_schema() -> None:
    """Apply sql/schema.sql idempotently. Voice Service owns `turns` (decision 040)."""
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
