"""Data-access layer for repositories.

No HTTP concerns here — no HTTPException, no FastAPI imports. Callers
(the router, or in the future, other internal code paths) get plain
Python return values or None, and translate to HTTP status codes themselves.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.repositories.models import Repository, RepositoryStatus


def create_repository(
    db: Session,
    *,
    owner_user_id: int,
    github_url: str,
) -> Repository:
    """Create a new repository row in `queued` state.

    The caller must have already checked for an existing row for this
    (owner, url) pair — the UniqueConstraint will otherwise raise
    IntegrityError. Kept explicit rather than swallowing here, because
    the correct HTTP response to a duplicate (409 with the existing row)
    needs the router to see it happen.
    """
    repo = Repository(
        owner_user_id=owner_user_id,
        github_url=github_url,
        status=RepositoryStatus.QUEUED.value,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


def get_repository_by_owner_and_url(
    db: Session,
    *,
    owner_user_id: int,
    github_url: str,
) -> Repository | None:
    """Look up a repository by its unique (owner, url) key."""
    stmt = select(Repository).where(
        Repository.owner_user_id == owner_user_id,
        Repository.github_url == github_url,
    )
    return db.scalars(stmt).one_or_none()


def get_repository_for_user(
    db: Session,
    *,
    repository_id: int,
    owner_user_id: int,
) -> Repository | None:
    """Fetch a repository by ID, scoped to the requesting user.

    Returns None if the repository doesn't exist OR belongs to someone else.
    The caller (router) turns None into 404 — never 403 — so we don't leak
    the existence of other users' resources (see design question 4).
    """
    stmt = select(Repository).where(
        Repository.id == repository_id,
        Repository.owner_user_id == owner_user_id,
    )
    return db.scalars(stmt).one_or_none()


def list_repositories_for_user(
    db: Session,
    *,
    owner_user_id: int,
) -> list[Repository]:
    """List all repositories owned by a user, newest first."""
    stmt = (
        select(Repository)
        .where(Repository.owner_user_id == owner_user_id)
        .order_by(Repository.created_at.desc())
    )
    return list(db.scalars(stmt))

# Add to core-api/src/core_api/repositories/service.py

class IllegalTransitionError(Exception):
    """Raised when an ingestion event would apply an illegal state transition.

    Domain-level exception — the internal router turns this into a 422
    response. Kept here (not in the router) so the service layer stays
    the single source of truth for the state machine, per decision 026.
    """


# Loose state machine (slice 3, revisiting decision 028):
# From non-terminal states any target is legal — this defends against
# out-of-order and dropped events without being strict about ordering.
# Terminal states reject everything, so a completed or failed ingestion
# can't be retroactively re-transitioned.
_LEGAL_SOURCE_STATES = frozenset(
    {RepositoryStatus.QUEUED, RepositoryStatus.IN_PROGRESS}
)

_EVENT_TO_TARGET = {
    "ingestion.started": RepositoryStatus.IN_PROGRESS,
    "ingestion.completed": RepositoryStatus.READY,
    "ingestion.failed": RepositoryStatus.FAILED,
}


def apply_ingestion_event(
    db: Session,
    *,
    repository_id: int,
    event_type: str,
    error_message: str | None = None,
) -> Repository | None:
    """Apply an ingestion status event to a repository row.

    Returns the updated Repository, or None if no repository with that
    ID exists. Raises IllegalTransitionError if the current state is
    terminal (`ready` or `failed`) and would otherwise be overwritten.

    `error_message` is only used for `ingestion.failed`. On non-failure
    transitions any stale `error_message` from a prior state is cleared
    so the UI never shows a resolved error next to a ready row.
    """
    target = _EVENT_TO_TARGET[event_type]

    # SELECT ... FOR UPDATE — we're about to check current state and
    # conditionally write. Row lock avoids a race where two callbacks
    # for the same repo interleave their read/write.
    stmt = select(Repository).where(Repository.id == repository_id).with_for_update()
    repo = db.scalars(stmt).one_or_none()
    if repo is None:
        return None

    current = RepositoryStatus(repo.status)
    if current not in _LEGAL_SOURCE_STATES:
        raise IllegalTransitionError(
            f"cannot apply {event_type} to repository in state {current.value}"
        )

    repo.status = target.value
    if target is RepositoryStatus.FAILED:
        repo.error_message = error_message or "ingestion failed"
    else:
        repo.error_message = None

    db.commit()
    db.refresh(repo)
    return repo