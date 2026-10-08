"""HTTP endpoints for interviews.

The router only speaks HTTP: it reads the request, calls the service,
and turns the result or exception into a status code.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from core_api.auth.dependencies import get_current_user
from core_api.db import get_db
from core_api.interviews import evaluation_client, service
from core_api.interviews.models import InterviewStatus
from core_api.interviews.schemas import (
    InterviewCreate,
    InterviewCreatedResponse,
    InterviewResponse,
    ReportResponse,
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


@router.get("", response_model=list[InterviewResponse])
def list_interviews(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[InterviewResponse]:
    """The current user's interviews, newest first. No tokens."""
    interviews = service.list_interviews_for_user(db, owner_user_id=current_user.id)
    return [InterviewResponse.model_validate(i) for i in interviews]


@router.get(
    "/{interview_id}",
    response_model=InterviewResponse,
    responses={404: {"description": "Interview not found"}},
)
def get_interview(
    interview_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InterviewResponse:
    """One of the current user's interviews. 404 if missing or not yours."""
    interview = service.get_interview_for_user(
        db,
        interview_id=interview_id,
        owner_user_id=current_user.id,
    )
    if interview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found",
        )
    return InterviewResponse.model_validate(interview)

_ENDED = (InterviewStatus.COMPLETED.value, InterviewStatus.INTERRUPTED.value)


def _generating(report: ReportResponse) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED, content=report.model_dump(mode="json")
    )


@router.get(
    "/{interview_id}/report",
    response_model=ReportResponse,
    responses={
        202: {"model": ReportResponse, "description": "Report is still being generated"},
        404: {"description": "Interview not found, or it has not ended"},
        503: {"description": "Evaluation Service unavailable"},
    },
)
def get_interview_report(
    interview_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportResponse | JSONResponse:
    """The interview's report, from Evaluation Service (decision 049).

    200 when `ready` or `failed`, 202 while `generating`. If Evaluation has
    no report for an ended interview, the trigger was lost: it is sent
    again here and the answer is 202 (lazy re-trigger).
    """
    interview = service.get_interview_for_user(
        db,
        interview_id=interview_id,
        owner_user_id=current_user.id,
    )
    if interview is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    if interview.status not in _ENDED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Interview is '{interview.status}'; reports exist once it has ended",
        )

    try:
        report = evaluation_client.get_report(interview.id)
        if report is None:
            evaluation_client.trigger_report(
                interview_id=interview.id,
                repository_id=interview.repository_id,
                outcome=interview.status,
            )
            return _generating(ReportResponse(interview_id=interview.id, status="generating"))
    except evaluation_client.EvaluationServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reports are unavailable right now; try again shortly",
        ) from exc

    response = ReportResponse.model_validate(report)
    if response.status == "generating":
        return _generating(response)
    return response
