"""Voice Service worker: plans interviews from SQS `plan.requested` jobs (decision 057).

Run with `python -m voice_service.worker`, from the same image as the API.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from pydantic import BaseModel
from repoviva_common.http import close_async_client, open_async_client
from repoviva_common.messaging import Message, close_messaging, open_messaging, run_worker
from repoviva_common.request_id import configure_logging

from voice_service.config import get_settings
from voice_service.db import close_db, ensure_indexes, get_db, init_db
from voice_service.planning.job import run_planning
from voice_service.session.store import SessionStore

logger = logging.getLogger(__name__)


class PlanRequested(BaseModel):
    """`data` of Core API's `plan.requested` job."""

    interview_id: int
    repository_id: int


async def handle_plan_requested(message: Message) -> None:
    """Claim, then plan. Claiming creates the plan or restarts a failed one;
    run_planning then runs unless the plan is `ready`, so a plan left
    `generating` by a crash reruns."""
    job = PlanRequested.model_validate(message.data)
    await SessionStore(get_db()).claim_plan(
        interview_id=job.interview_id, repository_id=job.repository_id
    )
    await run_planning(job.interview_id)


async def main() -> None:
    settings = get_settings()
    await init_db()
    await ensure_indexes()
    open_async_client()
    open_messaging(
        region=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url,
        access_key_id=settings.aws_access_key_id,
        secret_access_key=settings.aws_secret_access_key,
    )

    stop = asyncio.Event()
    # SIGTERM is how ECS stops a task; not supported by the event loop on Windows.
    with contextlib.suppress(NotImplementedError):
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop.set)

    logger.info("worker started: queue=%s", settings.planning_jobs_queue_url)
    try:
        await run_worker({settings.planning_jobs_queue_url: handle_plan_requested}, stop=stop)
    finally:
        close_messaging()
        await close_async_client()
        await close_db()


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
