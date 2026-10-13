"""Publishes `interview.ended` on EventBridge (decision 057).

Core API sets the interview's status from it and Evaluation Service starts
the report; Voice doesn't know either of them.
"""

from __future__ import annotations

from typing import Literal

from repoviva_common.messaging import publish_event_with_retry

from voice_service.config import get_settings

SOURCE = "repoviva.voice-service"
INTERVIEW_ENDED = "interview.ended"

Outcome = Literal["completed", "interrupted"]


class InterviewEventPublisher:
    def __init__(self, bus_name: str) -> None:
        self._bus_name = bus_name

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
        await publish_event_with_retry(
            self._bus_name,
            SOURCE,
            INTERVIEW_ENDED,
            {
                "interview_id": interview_id,
                "repository_id": repository_id,
                "outcome": outcome,
                "error_message": error_message,
            },
        )


def get_event_publisher() -> InterviewEventPublisher:
    return InterviewEventPublisher(get_settings().event_bus_name)
