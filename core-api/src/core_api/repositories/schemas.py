"""Pydantic schemas for the repositories API.

Kept separate from models.py because these are the *wire format*, not the
storage format. They can and should diverge — for instance, we never expose
owner_user_id in a response (the current user is implicit).
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

# Matches https://github.com/<owner>/<repo>, with optional trailing slash or .git suffix.
# Owner + repo names allow letters, digits, hyphens, underscores, periods.
# Deliberately permissive on the components; strict on the host.
GITHUB_URL_RE = re.compile(
    r"^https://github\.com/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+/?(?:\.git)?$"
)


class RepositoryCreate(BaseModel):
    """POST /v1/repositories body."""

    github_url: str

    @field_validator("github_url")
    @classmethod
    def validate_github_url(cls, v: str) -> str:
        v = v.strip()
        if not GITHUB_URL_RE.match(v):
            raise ValueError(
                "github_url must look like https://github.com/<owner>/<repo>"
            )
        # Normalize: strip trailing slash and .git so we store one canonical form.
        # Same URL submitted in slightly different shapes shouldn't create two rows.
        return v.rstrip("/").removesuffix(".git")


class RepositoryResponse(BaseModel):
    """What every repositories endpoint returns.

    Note what's NOT here: owner_user_id. The current user is implicit — the
    frontend already knows who they are.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    github_url: str
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime