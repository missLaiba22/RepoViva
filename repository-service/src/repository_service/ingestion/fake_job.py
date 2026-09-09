"""Placeholder ingestion job.

Real ingestion (clone, parse, chunk, embed) lands here later. For now the job
just sleeps between stages and emits the same lifecycle events the real one will,
so core-api can be wired up end to end.
"""

from __future__ import annotations

import asyncio
import logging

from repository_service.internal.core_api_client import CoreApiClient

logger = logging.getLogger(__name__)

# Stage name -> seconds to "work" before emitting it.
_STAGES: list[tuple[str, float]] = [
    ("ingestion.started", 0.0),
    ("ingestion.cloning", 0.5),
    ("ingestion.parsing", 0.5),
    ("ingestion.embedding", 0.5),
    ("ingestion.completed", 0.2),
]


async def run_fake_ingestion(
    repository_id: str,
    client: CoreApiClient,
    *,
    speed: float = 1.0,
) -> None:
    """Walk the fake pipeline, emitting one event per stage.

    ``speed`` scales the sleeps (tests pass ``speed=0`` to run instantly).
    """
    logger.info("starting fake ingestion for repository %s", repository_id)
    try:
        for stage, delay in _STAGES:
            if delay and speed:
                await asyncio.sleep(delay * speed)
            await client.emit_event(repository_id, {"type": stage})
    except Exception:  # noqa: BLE001 - report failure, then re-raise
        logger.exception("fake ingestion failed for repository %s", repository_id)
        try:
            await client.emit_event(repository_id, {"type": "ingestion.failed"})
        except Exception:  # noqa: BLE001 - don't mask the original error
            logger.exception("could not emit ingestion.failed for repository %s", repository_id)
        raise

    logger.info("finished fake ingestion for repository %s", repository_id)
