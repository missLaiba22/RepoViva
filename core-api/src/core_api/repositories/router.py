"""HTTP endpoints for repositories.

All endpoints require an authenticated session. Ownership is enforced
by the service layer — the router just supplies the current user's ID.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core_api.auth.dependencies import get_current_user
from core_api.db import get_db
from core_api.repositories import service
from core_api.repositories.schemas import RepositoryCreate, RepositoryResponse
from core_api.users.models import User

router = APIRouter(prefix="/v1/repositories", tags=["repositories"])


@router.post(
    "",
    response_model=RepositoryResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"description": "Repository already registered for this user"},
    },
)
def create_repository(
    payload: RepositoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RepositoryResponse:
    """Register a repository for ingestion.

    Idempotent by (user, github_url): resubmitting the same URL returns
    the existing repository with 409, not a duplicate row. This slice
    does NOT yet fire the ingest trigger — that lands in Step 4.
    """
    # Check for an existing row first — cheaper than catching IntegrityError,
    # and lets us return the existing repository in the 409 response.
    existing = service.get_repository_by_owner_and_url(
        db,
        owner_user_id=current_user.id,
        github_url=payload.github_url,
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Repository already registered",
                "repository": RepositoryResponse.model_validate(existing).model_dump(
                    mode="json"
                ),
            },
        )

    repo = service.create_repository(
        db,
        owner_user_id=current_user.id,
        github_url=payload.github_url,
    )
    return RepositoryResponse.model_validate(repo)


@router.get("", response_model=list[RepositoryResponse])
def list_repositories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RepositoryResponse]:
    """List the current user's repositories, newest first."""
    repos = service.list_repositories_for_user(db, owner_user_id=current_user.id)
    return [RepositoryResponse.model_validate(r) for r in repos]


@router.get("/{repository_id}", response_model=RepositoryResponse)
def get_repository(
    repository_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RepositoryResponse:
    """Fetch a single repository owned by the current user.

    Returns 404 if the repository doesn't exist OR belongs to another user.
    We deliberately do NOT return 403 for the second case — that would
    leak the existence of resources belonging to other users.
    """
    repo = service.get_repository_for_user(
        db,
        repository_id=repository_id,
        owner_user_id=current_user.id,
    )
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    return RepositoryResponse.model_validate(repo)