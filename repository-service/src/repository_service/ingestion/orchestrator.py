"""Runs the ingestion pipeline for a repository.

Called from the /ingest endpoint as a background task. Emits status
events to Core API at each stage boundary (see decision 026 and the
slice 3 close-out of decision 028).

Failure handling: any exception is caught, logged, and reported to
Core API as `ingestion.failed` before returning. Background tasks
that raise are silently dropped by FastAPI, so we catch here to
guarantee both a log line AND a status callback.
"""

from __future__ import annotations

import logging
from pathlib import Path

from repository_service.db import get_db_pool
from repository_service.indexing import run_indexing
from repository_service.ingestion.fetcher import FetchError, fetch_repository
from repository_service.internal.core_api_client import get_core_api_client

logger = logging.getLogger(__name__)


async def run_ingestion(
    *,
    repository_id: str,
    github_url: str,
    workspace_root: Path,
) -> None:
    logger.info(
        "ingestion started: repository_id=%s github_url=%s",
        repository_id, github_url,
    )
    client = get_core_api_client()

    await client.emit_event(repository_id, "ingestion.started")

    # --- Fetch ---
    try:
        fetch_result = await fetch_repository(
            repository_id=repository_id,
            github_url=github_url,
            workspace_root=workspace_root,
        )
    except FetchError as exc:
        logger.exception(
            "ingestion failed at fetch stage: repository_id=%s",
            repository_id,
        )
        await client.emit_event(
            repository_id, "ingestion.failed",
            data={"error_message": f"fetch failed: {exc}"},
        )
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "ingestion failed unexpectedly at fetch stage: repository_id=%s",
            repository_id,
        )
        await client.emit_event(
            repository_id, "ingestion.failed",
            data={"error_message": f"unexpected error: {exc}"},
        )
        return

    logger.info(
        "ingestion fetch complete: repository_id=%s clone_path=%s commit_sha=%s",
        repository_id, fetch_result.clone_path, fetch_result.commit_sha[:7],
    )

    # --- Indexing ---
    try:
        await run_indexing(
            repository_id=repository_id,
            commit_sha=fetch_result.commit_sha,
            source_dir=fetch_result.clone_path,
            pool=get_db_pool(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "ingestion failed at indexing stage: repository_id=%s",
            repository_id,
        )
        await client.emit_event(
            repository_id, "ingestion.failed",
            data={"error_message": f"indexing failed: {exc}"},
        )
        return

    logger.info("ingestion indexing complete: repository_id=%s", repository_id)

    await client.emit_event(repository_id, "ingestion.completed")
    logger.info("ingestion completed: repository_id=%s", repository_id)