"""Data-access and domain logic for interviews.

No HTTP concerns here — no HTTPException, no FastAPI imports. The router
translates return values and exceptions into status codes.
"""

from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from sqlalchemy.orm import Session

from core_api.config import get_settings
from core_api.interviews.models import Interview, InterviewStatus
from core_api.repositories.models import RepositoryStatus
from core_api.repositories.service import get_repository_for_user
from core_api.security.session_tokens import generate_session_token


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