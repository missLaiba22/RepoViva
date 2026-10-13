"""Publishes `interview.ended` on EventBridge (decision 057).

Core API sets the interview's status from it and Evaluation Service starts
the report; Voice doesn't know either of them.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from repoviva_common.messaging import MessagingError, publish_event

from voice_service.config import get_settings

logger = logging.getLogger(__name__)

SOURCE = "repoviva.voice-service"
INTERVIEW_ENDED = "interview.ended"

Outcome = Literal["completed", "interrupted"]

# Backoff between publish attempts. Retries are safe: consumers are idempotent.
_RETRY_DELAYS_S = (0.5, 2.0)


class InterviewEventPublisher:
    def __init__(self, bus_name: str, *, retry_delays_s: tuple[float, ...] = _RETRY_DELAYS_S):
        self._bus_name = bus_name
        self._retry_delays_s = retry_delays_s

    async def interview_ended(
        self,
        *,
        interview_id: int,
        repository_id: int,
        outcome: Outcome,
        error_message: str | None = None,
    ) -> None:
        """Best-effort after retries: a lost event leaves the interview `active`
        (decision 036's accepted risk); turns are already persisted."""
        data = {
            "interview_id": interview_id,
            "repository_id": repository_id,
            "outcome": outcome,
            "error_message": error_message,
        }
        for attempt, delay in enumerate((0.0, *self._retry_delays_s)):
            await asyncio.sleep(delay)
            try:
                await asyncio.to_thread(
                    publish_event, self._bus_name, SOURCE, INTERVIEW_ENDED, data
                )
                return
            except MessagingError:
                logger.warning(
                    "interview %s: publishing %s failed (attempt %d)",
                    interview_id, INTERVIEW_ENDED, attempt + 1, exc_info=True,
                )
        logger.error("interview %s: %s lost after retries", interview_id, INTERVIEW_ENDED)


def get_event_publisher() -> InterviewEventPublisher:
    return InterviewEventPublisher(get_settings().event_bus_name)
