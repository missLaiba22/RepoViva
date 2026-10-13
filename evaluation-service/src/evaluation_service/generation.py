"""Generate reports and record the outcome (decisions 049, 057).

Called by the worker for every `interview.ended` event and `report.requested`
job. A generation failure ends with the row marked `failed`; only when even
that can't be stored does it raise, so the message is redelivered.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from evaluation_service.clients.repository import get_repository_client
from evaluation_service.clients.voice import get_voice_client
from evaluation_service.db import get_db_pool
from evaluation_service.grading.llm import JsonLlm, get_llm
from evaluation_service.pipeline import ChunkSource, TurnSource, generate_report
from evaluation_service.reports import PendingReport, ReportStore

logger = logging.getLogger(__name__)

# Stored on the row and served through Core API, so it stays short.
_MAX_ERROR_LENGTH = 500


@dataclass(frozen=True)
class Dependencies:
    store: ReportStore
    voice: TurnSource
    repository: ChunkSource
    llm: JsonLlm


def default_dependencies() -> Dependencies:
    return Dependencies(
        store=ReportStore(get_db_pool()),
        voice=get_voice_client(),
        repository=get_repository_client(),
        llm=get_llm(),
    )


async def run_generation(
    report: PendingReport, deps: Dependencies | None = None
) -> None:
    """Generate one claimed report and store it as `ready` or `failed`."""
    deps = deps or default_dependencies()
    started = time.monotonic()
    try:
        content = await generate_report(
            interview_id=report.interview_id,
            repository_id=report.repository_id,
            partial=report.partial,
            voice=deps.voice,
            repository=deps.repository,
            llm=deps.llm,
        )
        await deps.store.mark_ready(report.interview_id, content)
    except Exception as exc:
        logger.exception("interview %d: report generation failed", report.interview_id)
        message = f"{type(exc).__name__}: {exc}"[:_MAX_ERROR_LENGTH]
        try:
            await deps.store.mark_failed(report.interview_id, message)
        except Exception:
            # The row stays `generating`: raise so the message is redelivered.
            logger.exception("interview %d: could not mark report failed", report.interview_id)
            raise
        return
    logger.info(
        "interview %d: report ready in %.0f s", report.interview_id, time.monotonic() - started
    )


async def request_report(report: PendingReport, deps: Dependencies | None = None) -> None:
    """Claim the report, then generate it unless it is already `ready` (decision 057).

    Claiming creates the row or restarts a failed one. A row still
    `generating` means the attempt holding the message died, so it reruns.
    """
    deps = deps or default_dependencies()
    claimed = await deps.store.claim(
        interview_id=report.interview_id,
        repository_id=report.repository_id,
        partial=report.partial,
    )
    if not claimed and await deps.store.get_status(report.interview_id) == "ready":
        logger.info("interview %d: report already ready, skipping", report.interview_id)
        return
    await run_generation(report, deps)
