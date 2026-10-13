"""Evaluation Service worker (decision 057).

Consumes `interview.ended` (the normal path) and `report.requested` jobs
(Core API's recovery and retry). Both claim the report and generate it.
Run with `python -m evaluation_service.worker`, from the same image as the API.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from typing import Literal

from pydantic import BaseModel
from repoviva_common.http import close_async_client, open_async_client
from repoviva_common.messaging import Message, close_messaging, open_messaging, run_worker

from evaluation_service.config import get_settings
from evaluation_service.db import apply_schema, close_pool, init_pool
from evaluation_service.generation import request_report
from evaluation_service.reports import PendingReport

logger = logging.getLogger(__name__)


class ReportRequested(BaseModel):
    """`data` of Core API's `report.requested` job."""

    interview_id: int
    repository_id: int
    outcome: Literal["completed", "interrupted"]


class InterviewEnded(ReportRequested):
    """`data` of Voice Service's `interview.ended` event."""

    error_message: str | None = None


def _pending(request: ReportRequested) -> PendingReport:
    return PendingReport(
        interview_id=request.interview_id,
        repository_id=request.repository_id,
        # An interrupted interview still gets a report, marked partial (decision 008).
        partial=request.outcome == "interrupted",
    )


async def handle_interview_ended(message: Message) -> None:
    await request_report(_pending(InterviewEnded.model_validate(message.data)))


async def handle_report_requested(message: Message) -> None:
    await request_report(_pending(ReportRequested.model_validate(message.data)))


async def main() -> None:
    settings = get_settings()
    await init_pool()
    await apply_schema()
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

    handlers = {
        settings.interview_events_queue_url: handle_interview_ended,
        settings.report_jobs_queue_url: handle_report_requested,
    }
    logger.info("worker started: queues=%s", list(handlers))
    try:
        await run_worker(handlers, stop=stop)
    finally:
        close_messaging()
        await close_async_client()
        await close_pool()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
