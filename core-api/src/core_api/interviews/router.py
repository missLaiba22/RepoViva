"""HTTP endpoints for interviews.

The router only speaks HTTP: it reads the request, calls the service,
and turns the result or exception into a status code.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core_api.auth.dependencies import get_current_user
from core_api.db import get_db
from core_api.interviews import service
from core_api.interviews.schemas import (
    InterviewCreate,
    InterviewCreatedResponse,
    InterviewResponse,
)
from core_api.users.models import User

router = APIRouter(prefix="/v1/interviews", tags=["interviews"])


@router.post(
    "",
    response_model=InterviewCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "Repository not found"},
        409: {"description": "Repository is not ready for interviews"},
    },
)
def create_interview(
    payload: InterviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InterviewCreatedResponse:
    """Start a new interview on one of the current user's ready repositories.

    The response contains the raw session token. It is shown only here,
    never again — Core API keeps only its hash (decision 035).
    """
    try:
        result = service.create_interview(
            db,
            owner_user_id=current_user.id,
            repository_id=payload.repository_id,
        )
    except service.RepositoryNotFoundError:
        # Same 404 whether it doesn't exist or isn't yours — don't leak.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )
    except service.RepositoryNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Repository is '{exc.status}'; interviews need a 'ready' repository",
        )

    base = InterviewResponse.model_validate(result.interview)
    return InterviewCreatedResponse(
        **base.model_dump(),
        session_token=result.raw_token,
        session_token_expires_at=result.interview.session_token_expires_at,
    )