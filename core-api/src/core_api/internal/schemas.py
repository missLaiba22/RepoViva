# core-api/src/core_api/internal/schemas.py
"""Pydantic schemas for internal service-to-service calls."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

EventType = Literal[
    "ingestion.started",
    "ingestion.completed",
    "ingestion.failed",
]


class IngestionEventBody(BaseModel):
    """Body of POST /internal/v1/repositories/{id}/events.

    Wire format from decisions 024–025 and architecture.md. Intentionally
    minimal for MVP — richer per-stage progress will land once the pipeline
    has real sub-stages worth reporting. `data` is a free-form dict:
    `error_message` is a convention on failure events, not enforced here.
    """

    event_id: UUID
    event_type: EventType
    occurred_at: datetime
    data: dict[str, Any] | None = None