from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db import Base


class RepositoryStatus(StrEnum):
    """Ingestion state machine — see decision 026.

    StrEnum: values ARE strings, so they serialize cleanly to JSON and
    round-trip through the DB without any coercion. `RepositoryStatus.QUEUED`
    IS the string "queued".
    """

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    READY = "ready"
    FAILED = "failed"


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Owner — CASCADE on delete: a user's repositories go with them.
    # See design discussion: orphaned repos are worse than the (rare) case
    # of accidentally deleting a user with valuable repo history.
    owner_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The GitHub URL the user submitted. Validated at the API boundary
    # (see repositories/schemas.py); this column just stores what was accepted.
    github_url: Mapped[str] = mapped_column(String(500), nullable=False)

    # State machine — String, not Postgres ENUM.
    # Consistency with users.github_login (also String) beats the marginal
    # strictness gain of ENUM, and avoids awkward Alembic migrations for
    # every new state added later (see decision 026).
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RepositoryStatus.QUEUED.value,
    )

    # Populated only when status transitions to `failed`.
    # Same-row (not a separate table) — one error per row, never queried alone.
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # A user can't register the same repo twice — the API returns
        # 409 Conflict pointing at the existing row instead.
        # Two different users independently registering the same public
        # repo is fine and is not caught by this constraint.
        UniqueConstraint("owner_user_id", "github_url", name="uq_repo_owner_url"),
    )