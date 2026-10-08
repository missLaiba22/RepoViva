"""Run report generation in the background and record the outcome (decision 049).

Called from the trigger endpoint through BackgroundTasks, and from the
lifespan for startup resume. Never raises: every failure ends with the
row marked `failed`, so the next trigger regenerates it.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from evaluation_service.clients.repository import RepositoryClient
from evaluation_service.clients.voice import VoiceClient
from evaluation_service.config import get_settings
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
    settings = get_settings()
    return Dependencies(
        store=ReportStore(get_db_pool()),
        voice=VoiceClient(settings.voice_service_base_url, settings.internal_hmac_secret),
        repository=RepositoryClient(
            settings.repository_service_base_url, settings.internal_hmac_secret
        ),
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
            # The row stays `generating`; startup resume picks it up.
            logger.exception("interview %d: could not mark report failed", report.interview_id)
        return
    logger.info(
        "interview %d: report ready in %.0f s", report.interview_id, time.monotonic() - started
    )


async def resume_generating(deps: Dependencies | None = None) -> None:
    """Startup resume: finish every report left `generating` by a crash or reload.

    One at a time, like the turns inside a report: the grading model's
    per-minute token budget is the bottleneck (decision 051).
    """
    deps = deps or default_dependencies()
    try:
        pending = await deps.store.list_generating()
    except Exception:
        logger.exception("startup resume: could not list unfinished reports")
        return
    if pending:
        logger.info("startup resume: %d unfinished report(s)", len(pending))
    for report in pending:
        await run_generation(report, deps)
