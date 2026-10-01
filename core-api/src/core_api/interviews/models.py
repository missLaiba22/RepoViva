from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db import Base


class InterviewStatus(StrEnum):
    """Interview lifecycle — see decision 036.

    created -> active -> completed
                      \\-> interrupted

    `expired` is deliberately not a state: nothing runs at expiry time to
    write it. A `created` interview past `session_token_expires_at` is
    expired by derivation.

    StrEnum: values ARE strings, so they serialize cleanly to JSON and
    round-trip through the DB without any coercion.
    """

    CREATED = "created"
    ACTIVE = "active"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Owner. Plain integer to match users.id (INTEGER) — BigInteger is only
    # for github_user_id. CASCADE: a user's interviews go with them, same
    # as their repositories.
    # Indexed for GET /v1/interviews (WHERE owner_user_id = ?).
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Repository being interviewed about. Plain integer to match
    # repositories.id.
    #
    # NO ACTION (explicit, not inherited): deleting a repository that has
    # interviews fails. A repository's data is spread across services
    # (code_chunks in Repository Service, turns in Voice Service), which a
    # database cascade cannot reach — so repository deletion must be a
    # deliberate cross-service flow, not a side effect of one DELETE.
    # NO ACTION rather than RESTRICT: NO ACTION checks at the end of the
    # statement, so deleting a user (which cascades to both repositories
    # and interviews in one statement) still works.
    #
    # Indexed even though no endpoint filters by repository_id: Postgres
    # does not index foreign keys automatically, and without this index
    # the FK check on a repository delete scans the whole table.
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="NO ACTION"),
        nullable=False,
        index=True,
    )

    # String + StrEnum, not a Postgres ENUM — same reasoning as
    # repositories.status (decision 026). Strict transitions are enforced
    # in the service layer (decision 036).
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=InterviewStatus.CREATED.value,
    )

    # Set only when status becomes `interrupted` because of an error.
    error_message: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    # Hex-encoded SHA-256 of the one-time session token (always 64 chars).
    # The raw token is returned to the client once and never stored
    # (decision 035). Uniqueness is declared in __table_args__ with an
    # explicit name.
    # Served by the unique index: consume endpoint
    # (WHERE session_token_hash = ?).
    session_token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    # The token cannot be consumed after this time.
    session_token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Set when the token is consumed. This is also the interview start
    # time — there is deliberately no separate started_at (decision 036).
    session_token_consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Set when the interview reaches a terminal state (completed or
    # interrupted).
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        # Explicit name: db.py sets no naming convention, so an unnamed
        # unique constraint gets a generated name that Alembic autogenerate
        # keeps re-detecting as drift (see architecture.md, Future
        # Evolution). Same approach as uq_repo_owner_url.
        UniqueConstraint("session_token_hash", name="uq_interviews_session_token_hash"),
    )