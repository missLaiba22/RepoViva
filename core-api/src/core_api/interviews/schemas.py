"""Pydantic schemas for the interviews API — the wire format, not storage.

Never in any response: session_token_hash (a secret's fingerprint) and
owner_user_id (the current user is implicit — same rule as repositories).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InterviewCreate(BaseModel):
    """POST /v1/interviews body."""

    repository_id: int = Field(gt=0)


class InterviewResponse(BaseModel):
    """What every interviews endpoint returns. Contains no token."""

    model_config = ConfigDict(
        from_attributes=True,
        validate_by_alias=True,
        validate_by_name=True,
    )

    id: int
    repository_id: int
    status: str
    error_message: str | None
    # Stored as session_token_consumed_at (decision 036); clients just see
    # "when did it start", so it's renamed on the way out.
    started_at: datetime | None = Field(validation_alias="session_token_consumed_at")
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InterviewCreatedResponse(InterviewResponse):
    """Returned ONLY by POST /v1/interviews — the one time the raw token
    is ever shown. No other endpoint uses this schema."""

    session_token: str
    session_token_expires_at: datetime