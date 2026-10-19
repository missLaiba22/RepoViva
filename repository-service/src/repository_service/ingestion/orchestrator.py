"""Runs the ingestion pipeline for a repository.

Called by the worker for each `ingestion.requested` job (decision 057).
Publishes status events at each stage boundary (decisions 026, 057).
Pipeline errors are caught and reported as `ingestion.failed`; only a crash
leaves the job `in_progress`, so the redelivered message reruns it, up to
`MAX_ATTEMPTS`. A redelivered `ready` job publishes its outcome again, so a
lost final event is never final (decision 058); a `failed` one is restarted
by its claim and runs again (decision 061).
"""

from __future__ import annotations

import asyncio
import logging

from repository_service.clients.events import IngestionEventPublisher, get_event_publisher
from repository_service.config import get_settings
from repository_service.db import get_db_pool
from repository_service.indexing import RepositoryTooLargeError, run_indexing
from repository_service.ingestion import jobs
from repository_service.ingestion.fetcher import FetchError, fetch_repository
from repository_service.ingestion.jobs import IngestionJob, JobStatus
from repository_service.ingestion.workspace import remove_workspace

logger = logging.getLogger(__name__)

CRASHED_MESSAGE = "ingestion stopped after repeated crashes"


class OutcomeNotPublishedError(Exception):
    """The final event was lost; raised so SQS redelivers the job."""


async def run_ingestion(repository_id: str) -> None:
    pool = get_db_pool()
    job = await jobs.get(pool, repository_id)
    if job is None:
        logger.warning("no ingestion job: repository_id=%s", repository_id)
        return
    events = get_event_publisher()
    if job.status in jobs.TERMINAL:
        logger.info(
            "ingestion already %s, publishing it again: repository_id=%s",
            job.status, repository_id,
        )
        await _publish_outcome(events, repository_id, job.status, job.error_message)
        return

    if job.attempts > jobs.MAX_ATTEMPTS:
        logger.error(
            "ingestion crashed %d times, failing it: repository_id=%s",
            job.attempts - 1, repository_id,
        )
        await jobs.set_status(pool, repository_id, JobStatus.FAILED, CRASHED_MESSAGE)
        await _publish_outcome(events, repository_id, JobStatus.FAILED, CRASHED_MESSAGE)
        return

    logger.info(
        "ingestion started: repository_id=%s github_url=%s attempt=%d",
        repository_id, job.github_url, job.attempts,
    )
    await events.emit_event(repository_id, "ingestion.started")

    error_message = await _ingest(job)

    status = JobStatus.READY if error_message is None else JobStatus.FAILED
    await jobs.set_status(pool, repository_id, status, error_message)
    await _publish_outcome(events, repository_id, status, error_message)
    logger.info("ingestion %s: repository_id=%s", status, repository_id)


async def _publish_outcome(
    events: IngestionEventPublisher,
    repository_id: str,
    status: JobStatus,
    error_message: str | None,
) -> None:
    if status is JobStatus.READY:
        published = await events.emit_event(repository_id, "ingestion.completed")
    else:
        published = await events.emit_event(
            repository_id, "ingestion.failed", error_message=error_message,
        )
    if not published:
        raise OutcomeNotPublishedError(f"{status} event for repository {repository_id} lost")


async def _ingest(job: IngestionJob) -> str | None:
    """Fetch and index the repository. Returns an error message, or None on success."""
    workspace_root = get_settings().workspace_root
    try:
        return await _fetch_and_index(job)
    finally:
        # Everything after ingestion reads Postgres; the clone is only scratch space.
        await asyncio.to_thread(remove_workspace, job.repository_id, workspace_root)


async def _fetch_and_index(job: IngestionJob) -> str | None:
    repository_id = job.repository_id
    try:
        fetch_result = await fetch_repository(
            repository_id=repository_id,
            github_url=job.github_url,
            workspace_root=get_settings().workspace_root,
        )
    except FetchError as exc:
        logger.exception("ingestion failed at fetch stage: repository_id=%s", repository_id)
        return f"fetch failed: {exc}"
    except Exception as exc:
        logger.exception(
            "ingestion failed unexpectedly at fetch stage: repository_id=%s", repository_id,
        )
        return f"unexpected error: {exc}"

    logger.info(
        "ingestion fetch complete: repository_id=%s clone_path=%s commit_sha=%s",
        repository_id, fetch_result.clone_path, fetch_result.commit_sha[:7],
    )

    try:
        await run_indexing(
            repository_id=repository_id,
            commit_sha=fetch_result.commit_sha,
            source_dir=fetch_result.clone_path,
            pool=get_db_pool(),
        )
    except RepositoryTooLargeError as exc:
        # Expected, user-facing rejection (decision 033) — no traceback.
        logger.warning("ingestion rejected: repository_id=%s %s", repository_id, exc)
        return str(exc)
    except Exception as exc:
        logger.exception("ingestion failed at indexing stage: repository_id=%s", repository_id)
        return f"indexing failed: {exc}"

    logger.info("ingestion indexing complete: repository_id=%s", repository_id)
    return None
