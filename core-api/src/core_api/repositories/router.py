"""HTTP endpoints for repositories.

All endpoints require an authenticated session. Ownership is enforced
by the service layer — the router just supplies the current user's ID.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core_api.auth.dependencies import get_current_user
from core_api.db import get_db
from core_api.repositories import service
from core_api.repositories.ingestion_client import (
    IngestionTriggerError,
    trigger_ingestion,
)
from core_api.repositories.models import RepositoryStatus
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
    the existing repository with 409, not a duplicate row.

    After creating the row, fires an HMAC-signed trigger to Repository
    Service to start ingestion. If that call fails, the row is marked
    `failed` immediately (see design question 2 in Step 4 and decision 028).
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

    # Create the row in `queued` state.
    repo = service.create_repository(
        db,
        owner_user_id=current_user.id,
        github_url=payload.github_url,
    )

    # Fire the trigger to Repository Service. If this fails, we mark the
    # row `failed` immediately and return it to the user — the alternatives
    # (roll back the row, or leave it silently stuck in `queued`) are worse.
    # See design question 2 in Step 4 and decision 028.
    try:
        trigger_ingestion(repository_id=repo.id, github_url=repo.github_url)
    except IngestionTriggerError as exc:
        repo.status = RepositoryStatus.FAILED.value
        repo.error_message = f"could not start ingestion: {exc}"
        db.commit()
        db.refresh(repo)

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