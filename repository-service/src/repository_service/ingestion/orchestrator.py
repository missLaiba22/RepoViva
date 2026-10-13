"""Runs the ingestion pipeline for a repository.

Called by the worker for each `ingestion.requested` job (decision 057).
Publishes status events at each stage boundary (decisions 026, 057).
Pipeline errors are caught and reported as `ingestion.failed`; only a crash
leaves the job `in_progress`, so the redelivered message reruns it.
"""

from __future__ import annotations

import logging

from repository_service.clients.events import get_event_publisher
from repository_service.config import get_settings
from repository_service.db import get_db_pool
from repository_service.indexing import RepositoryTooLargeError, run_indexing
from repository_service.ingestion import jobs
from repository_service.ingestion.fetcher import FetchError, fetch_repository
from repository_service.ingestion.jobs import IngestionJob, JobStatus

logger = logging.getLogger(__name__)


async def run_ingestion(repository_id: str) -> None:
    pool = get_db_pool()
    job = await jobs.get(pool, repository_id)
    if job is None:
        logger.warning("no ingestion job: repository_id=%s", repository_id)
        return
    if job.status in jobs.TERMINAL:
        logger.info(
            "ingestion already %s, skipping: repository_id=%s", job.status, repository_id,
        )
        return

    logger.info(
        "ingestion started: repository_id=%s github_url=%s", repository_id, job.github_url,
    )
    events = get_event_publisher()
    await events.emit_event(repository_id, "ingestion.started")

    error_message = await _ingest(job)

    if error_message is None:
        await jobs.set_status(pool, repository_id, JobStatus.READY)
        await events.emit_event(repository_id, "ingestion.completed")
        logger.info("ingestion completed: repository_id=%s", repository_id)
    else:
        await jobs.set_status(pool, repository_id, JobStatus.FAILED)
        await events.emit_event(repository_id, "ingestion.failed", error_message=error_message)


async def _ingest(job: IngestionJob) -> str | None:
    """Fetch and index the repository. Returns an error message, or None on success."""
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
