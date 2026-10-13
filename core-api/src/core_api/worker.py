"""Core API worker: consumes `interview.ended` from SQS (decision 057).

Run with `python -m core_api.worker`, from the same image as the API.
Core API is sync, so each handler runs in a thread.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from typing import Literal

from pydantic import BaseModel
from repoviva_common.messaging import Message, close_messaging, open_messaging, run_worker

from core_api.config import get_settings
from core_api.db import SessionLocal
from core_api.interviews import service as interviews_service

# Interview's foreign keys name these tables; SQLAlchemy resolves them only
# if their models are loaded. The API loads them through its routers.
from core_api.repositories import models as _repositories_models  # noqa: F401
from core_api.users import models as _users_models  # noqa: F401

logger = logging.getLogger(__name__)


class InterviewEnded(BaseModel):
    """`data` of Voice Service's `interview.ended` event."""

    interview_id: int
    repository_id: int
    outcome: Literal["completed", "interrupted"]
    error_message: str | None = None


def end_interview(event: InterviewEnded) -> None:
    """Duplicates and late events are expected: an interview that has
    already ended, or doesn't exist, is handled by doing nothing."""
    with SessionLocal() as db:
        try:
            interview = interviews_service.end_interview(
                db,
                interview_id=event.interview_id,
                outcome=event.outcome,
                error_message=event.error_message,
            )
        except interviews_service.IllegalTransitionError as exc:
            logger.info("interview %d: end event ignored: %s", event.interview_id, exc)
            return
    if interview is None:
        logger.warning("interview %d: end event for unknown interview", event.interview_id)


async def handle_interview_ended(message: Message) -> None:
    await asyncio.to_thread(end_interview, InterviewEnded.model_validate(message.data))


async def main() -> None:
    settings = get_settings()
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

    logger.info("worker started: queue=%s", settings.interview_events_queue_url)
    try:
        await run_worker({settings.interview_events_queue_url: handle_interview_ended}, stop=stop)
    finally:
        close_messaging()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
