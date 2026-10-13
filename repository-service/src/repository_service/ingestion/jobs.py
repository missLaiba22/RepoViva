"""Stored state of ingestion jobs (decision 057)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import asyncpg


class JobStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    READY = "ready"
    FAILED = "failed"


TERMINAL = frozenset({JobStatus.READY, JobStatus.FAILED})


@dataclass(frozen=True)
class IngestionJob:
    repository_id: str
    github_url: str
    status: JobStatus


_CLAIM = """
INSERT INTO ingestion_jobs (repository_id, github_url, status)
VALUES ($1, $2, 'in_progress')
ON CONFLICT (repository_id) DO NOTHING
"""

_GET = "SELECT repository_id, github_url, status FROM ingestion_jobs WHERE repository_id = $1"

_SET_STATUS = """
UPDATE ingestion_jobs SET status = $2, updated_at = now() WHERE repository_id = $1
"""


async def claim(pool: asyncpg.Pool, *, repository_id: str, github_url: str) -> None:
    """Create the job row; does nothing if it already exists."""
    async with pool.acquire() as conn:
        await conn.execute(_CLAIM, repository_id, github_url)


async def get(pool: asyncpg.Pool, repository_id: str) -> IngestionJob | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET, repository_id)
    if row is None:
        return None
    return IngestionJob(row["repository_id"], row["github_url"], JobStatus(row["status"]))


async def set_status(pool: asyncpg.Pool, repository_id: str, status: JobStatus) -> None:
    async with pool.acquire() as conn:
        await conn.execute(_SET_STATUS, repository_id, status.value)
