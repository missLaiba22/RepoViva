"""Integration tests for jobs.claim against a real Postgres (decisions 058, 061).

Skipped if the database is unreachable.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest

from repository_service.config import get_settings
from repository_service.db import _SCHEMA_SQL_PATH
from repository_service.ingestion import jobs
from repository_service.ingestion.jobs import JobStatus

pytestmark = pytest.mark.integration

URL = "https://github.com/a/b"


@pytest.fixture
async def pool():
    try:
        pool = await asyncpg.create_pool(get_settings().database_url)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Postgres unavailable: {exc}")
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL_PATH.read_text())
    yield pool
    await pool.close()


@pytest.fixture
async def repository_id(pool):
    rid = f"test-claim-{uuid.uuid4().hex[:8]}"
    yield rid
    await pool.execute("DELETE FROM ingestion_jobs WHERE repository_id = $1", rid)


async def test_redelivery_counts_another_attempt(pool, repository_id):
    await jobs.claim(pool, repository_id=repository_id, github_url=URL)
    await jobs.claim(pool, repository_id=repository_id, github_url=URL)

    job = await jobs.get(pool, repository_id)
    assert (job.status, job.attempts) == (JobStatus.IN_PROGRESS, 2)


async def test_failed_job_restarts_as_a_first_attempt(pool, repository_id):
    await jobs.claim(pool, repository_id=repository_id, github_url=URL)
    await jobs.claim(pool, repository_id=repository_id, github_url=URL)
    await jobs.set_status(pool, repository_id, JobStatus.FAILED, "fetch failed: x")

    await jobs.claim(pool, repository_id=repository_id, github_url=URL)

    job = await jobs.get(pool, repository_id)
    assert (job.status, job.attempts, job.error_message) == (JobStatus.IN_PROGRESS, 1, None)


async def test_ready_job_is_left_alone(pool, repository_id):
    await jobs.claim(pool, repository_id=repository_id, github_url=URL)
    await jobs.set_status(pool, repository_id, JobStatus.READY)

    await jobs.claim(pool, repository_id=repository_id, github_url=URL)

    job = await jobs.get(pool, repository_id)
    assert (job.status, job.attempts) == (JobStatus.READY, 1)
