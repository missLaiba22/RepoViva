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