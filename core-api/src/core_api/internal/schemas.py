# core-api/src/core_api/internal/schemas.py
"""Pydantic schemas for internal service-to-service calls."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

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


class SessionTokenConsumeBody(BaseModel):
    """Body of POST /internal/v1/session-tokens/consume (decision 035)."""

    # token_urlsafe(32) is 43 chars. The cap stops a caller making us
    # hash arbitrarily large input; 128 leaves room if the format grows.
    token: str = Field(min_length=1, max_length=128)


class SessionTokenConsumeResponse(BaseModel):
    """200 response: what Voice Service needs to run the session."""

    interview_id: int
    user_id: int
    repository_id: int