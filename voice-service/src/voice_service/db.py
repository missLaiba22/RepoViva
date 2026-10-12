"""FastAPI-owned MongoDB client for Voice Service (decision 053).

Opened in main.py's lifespan and closed on shutdown, the same shape as
the other services' Postgres pools. Code reaches the database through
get_db().
"""

from __future__ import annotations

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from voice_service.config import get_settings

SESSIONS = "interview_sessions"

_client: AsyncMongoClient | None = None


async def init_db() -> None:
    global _client
    _client = AsyncMongoClient(get_settings().mongodb_uri, tz_aware=True)


async def ensure_indexes() -> None:
    """Idempotent: safe on every boot. One session document per interview."""
    await get_db()[SESSIONS].create_index("interview_id", unique=True)


async def close_db() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def get_db() -> AsyncDatabase:
    if _client is None:
        raise RuntimeError("MongoDB client not initialized — check FastAPI lifespan")
    return _client[get_settings().mongodb_database]
