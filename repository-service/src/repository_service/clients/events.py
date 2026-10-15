"""Publishes ingestion status events on EventBridge (decision 057).

Core API consumes them from its own queue to update the repository's
user-visible status (decision 024).
"""

from __future__ import annotations

from typing import Literal

from repoviva_common.messaging import publish_event_with_retry

from repository_service.config import get_settings

SOURCE = "repoviva.repository-service"

IngestionEventType = Literal["ingestion.started", "ingestion.completed", "ingestion.failed"]


class IngestionEventPublisher:
    def __init__(self, bus_name: str) -> None:
        self._bus_name = bus_name

    async def emit_event(
        self,
        repository_id: str,
        event_type: IngestionEventType,
        *,
        error_message: str | None = None,
    ) -> bool:
        """False if every retry failed. A lost `started` is harmless (decision 029);
        the caller makes a lost final event redeliver the job (decision 058)."""
        return await publish_event_with_retry(
            self._bus_name,
            SOURCE,
            event_type,
            {"repository_id": int(repository_id), "error_message": error_message},
        )


def get_event_publisher() -> IngestionEventPublisher:
    return IngestionEventPublisher(get_settings().event_bus_name)
