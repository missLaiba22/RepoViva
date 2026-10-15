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
# Below the queue's maxReceiveCount (3), so the last delivery fails the job (decision 058).
MAX_ATTEMPTS = 2


@dataclass(frozen=True)
class IngestionJob:
    repository_id: str
    github_url: str
    status: JobStatus
    attempts: int = 1
    error_message: str | None = None


_CLAIM = """
INSERT INTO ingestion_jobs (repository_id, github_url, status)
VALUES ($1, $2, 'in_progress')
ON CONFLICT (repository_id) DO UPDATE
SET attempts = ingestion_jobs.attempts + 1, updated_at = now()
WHERE ingestion_jobs.status = 'in_progress'
"""

_GET = """
SELECT repository_id, github_url, status, attempts, error_message
FROM ingestion_jobs WHERE repository_id = $1
"""

_SET_STATUS = """
UPDATE ingestion_jobs SET status = $2, error_message = $3, updated_at = now()
WHERE repository_id = $1
"""


async def claim(pool: asyncpg.Pool, *, repository_id: str, github_url: str) -> None:
    """Create the job row, or count another attempt if it is still in progress."""
    async with pool.acquire() as conn:
        await conn.execute(_CLAIM, repository_id, github_url)


async def get(pool: asyncpg.Pool, repository_id: str) -> IngestionJob | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET, repository_id)
    if row is None:
        return None
    return IngestionJob(
        row["repository_id"], row["github_url"], JobStatus(row["status"]),
        row["attempts"], row["error_message"],
    )


async def set_status(
    pool: asyncpg.Pool, repository_id: str, status: JobStatus, error_message: str | None = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(_SET_STATUS, repository_id, status.value, error_message)
