# core-api/src/core_api/internal/schemas.py
"""Pydantic schemas for internal service-to-service calls."""

from __future__ import annotations

from pydantic import BaseModel, Field


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