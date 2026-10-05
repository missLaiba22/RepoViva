"""Data-access and domain logic for interviews.

No HTTP concerns here — no HTTPException, no FastAPI imports. The router
translates return values and exceptions into status codes.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal, NamedTuple

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from core_api.config import get_settings
from core_api.interviews.models import Interview, InterviewStatus
from core_api.repositories.models import RepositoryStatus
from core_api.repositories.service import get_repository_for_user
from core_api.security.session_tokens import (
    generate_session_token,
    hash_session_token,
)

logger = logging.getLogger(__name__)


class RepositoryNotFoundError(Exception):
    """The repository doesn't exist, or belongs to someone else.

    One error for both cases: the router answers 404 either way, so we
    never reveal that another user's repository exists.
    """


class RepositoryNotReadyError(Exception):
    """The repository exists but isn't `ready` — nothing to interview on.

    Router answers 409: the request is valid, the resource's state isn't.
    """

    def __init__(self, status: str) -> None:
        super().__init__(f"Repository is '{status}', not 'ready'")
        self.status = status


class CreatedInterview(NamedTuple):
    """The saved interview plus the raw session token.

    The raw token exists only here, in memory: the Interview row stores
    just its hash. If the service returned only the Interview, the raw
    token would be lost and the client could never connect.
    """

    interview: Interview
    raw_token: str


def create_interview(
    db: Session,
    *,
    owner_user_id: int,
    repository_id: int,
) -> CreatedInterview:
    """Create an interview in `created` state with a one-time session token.

    Raises RepositoryNotFoundError or RepositoryNotReadyError if the
    repository can't be interviewed on.
    """
    # 1. Find the repository, scoped to this user.
    repo = get_repository_for_user(
        db,
        repository_id=repository_id,
        owner_user_id=owner_user_id,
    )
    if repo is None:
        raise RepositoryNotFoundError()

    # 2. Only a fully ingested repository has code to ask about.
    if repo.status != RepositoryStatus.READY.value:
        raise RepositoryNotReadyError(repo.status)

    # 3. Token: raw goes to the client, hash goes to the database.
    token = generate_session_token()

    # 4. Expiry applies to the token, not the interview (decision 036).
    ttl = timedelta(minutes=get_settings().session_token_ttl_minutes)
    expires_at = datetime.now(timezone.utc) + ttl

    # 5. Save — the hash only, never the raw token.
    interview = Interview(
        owner_user_id=owner_user_id,
        repository_id=repository_id,
        status=InterviewStatus.CREATED.value,
        session_token_hash=token.hash,
        session_token_expires_at=expires_at,
    )
    db.add(interview)
    db.commit()
    db.refresh(interview)

    # 6. Hand back both; the router decides how to present them.
    return CreatedInterview(interview=interview, raw_token=token.raw)


# --- Session token consumption (decision 035) -------------------------------

RejectionReason = Literal["unknown", "expired", "consumed"]


class ConsumedSession(NamedTuple):
    """What Voice Service needs to run the session (decision 035)."""

    interview_id: int
    user_id: int
    repository_id: int


class TokenRejectedError(Exception):
    """The token can't start a session. Router answers 403 with the reason.

    The reason is for Voice Service's logs only — the end user always sees
    one generic close (decision 035). `consumed` is the one worth watching:
    it's the replay / leaked-token signal.
    """

    def __init__(self, reason: RejectionReason) -> None:
        super().__init__(f"Session token rejected: {reason}")
        self.reason = reason


def consume_session_token(db: Session, *, raw_token: str) -> ConsumedSession:
    """Validate and consume a session token in ONE statement.

    Check and write are a single UPDATE, so two concurrent requests with
    the same token cannot both succeed: under Read Committed the loser
    waits for the winner's commit, re-checks its WHERE, and matches
    nothing. Also moves the interview created -> active (decision 036).
    """
    token_hash = hash_session_token(raw_token)

    stmt = (
        update(Interview)
        .where(
            Interview.session_token_hash == token_hash,
            Interview.session_token_consumed_at.is_(None),
            Interview.session_token_expires_at > func.now(),  # DB clock
            Interview.status == InterviewStatus.CREATED.value,  # only legal entry to active
        )
        .values(
            session_token_consumed_at=func.now(),  # doubles as start time (036)
            status=InterviewStatus.ACTIVE.value,
        )
        .returning(Interview.id, Interview.owner_user_id, Interview.repository_id)
        # No Interview objects are loaded in this session, so there is
        # nothing in memory to keep in sync with the UPDATE.
        .execution_options(synchronize_session=False)
    )
    row = db.execute(stmt).one_or_none()

    if row is None:
        reason = _classify_rejection(db, token_hash)
        db.rollback()  # nothing was written; end the transaction cleanly
        raise TokenRejectedError(reason)

    # Commit BEFORE returning: the token is burned the moment we say yes.
    # If anything fails after this, the interview is stuck `active` — the
    # risk decision 036 accepted — but the token can never be used twice.
    db.commit()
    return ConsumedSession(
        interview_id=row.id,
        user_id=row.owner_user_id,
        repository_id=row.repository_id,
    )


def _classify_rejection(db: Session, token_hash: str) -> RejectionReason:
    """Explain why the consume UPDATE matched nothing.

    Order matters: consumed before expired. Both columns only move one way
    (consumed_at never un-sets; expiry never un-happens), and a token
    can't be consumed after expiring, so checking consumed first gives
    the right answer even if another request won the race a moment ago.
    Runs in the same transaction as the UPDATE, so Postgres's now()
    (transaction start time) is identical for both.
    """
    row = db.execute(
        select(
            Interview.session_token_consumed_at,
            (Interview.session_token_expires_at <= func.now()).label("is_expired"),
            Interview.status,
        ).where(Interview.session_token_hash == token_hash)
    ).one_or_none()

    if row is None:
        return "unknown"
    if row.session_token_consumed_at is not None:
        return "consumed"
    if row.is_expired:
        return "expired"

    # Unused, unexpired, yet the UPDATE missed: only possible if status
    # isn't `created`, which our invariants say can't happen. Shout.
    logger.error(
        "Session token unused and unexpired but not consumable; status=%s",
        row.status,
    )
    return "unknown"