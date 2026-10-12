"""Plan an interview's questions in the background (decision 052).

Called from the trigger endpoint through BackgroundTasks, and from the
lifespan for startup resume. Takes only the interview id and loads the
rest, and does nothing unless the plan is `generating`, so a rerun is
harmless. Never raises: every failure ends with the plan `failed`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Protocol

from voice_service.clients.repository import Area, Chunk, get_repository_client
from voice_service.config import get_settings
from voice_service.db import get_db
from voice_service.planning.planner import get_planner
from voice_service.planning.prompts import AREA_QUERY, AreaContext
from voice_service.session.store import PlannedQuestion, SessionStore

logger = logging.getLogger(__name__)

# Served to the live page through Core API, so it stays short.
_MAX_ERROR_LENGTH = 500
# Decision 052: a transient failure is retried once automatically.
_ATTEMPTS = 2


class Repository(Protocol):
    async def list_areas(self, repository_id: int, *, limit: int) -> list[Area]: ...
    async def retrieve(
        self, repository_id: int, query: str, *, top_k: int, filename_prefix: str
    ) -> list[Chunk]: ...


class PlanWriter(Protocol):
    async def write_plan(self, areas: list[AreaContext]) -> list[PlannedQuestion]: ...


class NothingToAskError(Exception):
    """Permanent: the repository has no code to plan from. Retrying can't help."""


@dataclass(frozen=True)
class Dependencies:
    store: SessionStore
    repository: Repository
    planner: PlanWriter
    max_questions: int
    chunks_per_area: int


def default_dependencies() -> Dependencies:
    settings = get_settings()
    return Dependencies(
        store=SessionStore(get_db()),
        repository=get_repository_client(),
        planner=get_planner(),
        max_questions=settings.max_questions,
        chunks_per_area=settings.plan_chunks_per_area,
    )


async def run_planning(interview_id: int, deps: Dependencies | None = None) -> None:
    """Write and store the interview's plan, or mark it `failed`."""
    deps = deps or default_dependencies()
    started = time.monotonic()
    try:
        job = await deps.store.get_plan_job(interview_id)
        if job is None or job.plan_status != "generating":
            return  # already done, or never triggered
        for attempt in range(1, _ATTEMPTS + 1):
            await deps.store.count_attempt(interview_id)
            try:
                questions = await _plan(job.repository_id, deps)
                break
            except NothingToAskError:
                raise
            except Exception:
                if attempt == _ATTEMPTS:
                    raise
                logger.warning(
                    "interview %d: planning attempt %d failed, retrying",
                    interview_id, attempt, exc_info=True,
                )
        await deps.store.save_plan(interview_id, questions)
    except Exception as exc:
        logger.exception("interview %d: planning failed", interview_id)
        await _mark_failed(deps.store, interview_id, exc)
        return
    logger.info(
        "interview %d: plan of %d questions ready in %.1f s",
        interview_id, len(questions), time.monotonic() - started,
    )


async def _plan(repository_id: int, deps: Dependencies) -> list[PlannedQuestion]:
    areas = await deps.repository.list_areas(repository_id, limit=deps.max_questions)
    if not areas:
        raise NothingToAskError("the repository has no indexed code")

    chunk_lists = await asyncio.gather(*(
        deps.repository.retrieve(
            repository_id, AREA_QUERY, top_k=deps.chunks_per_area, filename_prefix=area.path
        )
        for area in areas
    ))
    contexts = [
        AreaContext(area.path, chunks)
        for area, chunks in zip(areas, chunk_lists, strict=True)
        if chunks
    ]
    if not contexts:
        raise NothingToAskError("no code was found in any area of the repository")
    return await deps.planner.write_plan(contexts)


async def _mark_failed(store: SessionStore, interview_id: int, exc: Exception) -> None:
    retryable = not isinstance(exc, NothingToAskError)
    message = (str(exc) if not retryable else f"{type(exc).__name__}: {exc}")[:_MAX_ERROR_LENGTH]
    try:
        await store.fail_plan(interview_id, message, retryable=retryable)
    except Exception:
        # The plan stays `generating`; startup resume picks it up.
        logger.exception("interview %d: could not mark plan failed", interview_id)


async def resume_planning(deps: Dependencies | None = None) -> None:
    """Startup resume: finish every plan left `generating` by a crash or reload."""
    deps = deps or default_dependencies()
    try:
        pending = await deps.store.list_generating()
    except Exception:
        logger.exception("startup resume: could not list unfinished plans")
        return
    if pending:
        logger.info("startup resume: %d unfinished plan(s)", len(pending))
    for interview_id in pending:
        await run_planning(interview_id, deps)
