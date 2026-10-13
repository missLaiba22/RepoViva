"""HTTP endpoints for interviews.

The router only speaks HTTP: it reads the request, calls the service,
and turns the result or exception into a status code.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from core_api.auth.dependencies import get_current_user
from core_api.db import get_db
from core_api.interviews import evaluation_client, service, voice_client
from core_api.interviews.models import InterviewStatus
from core_api.interviews.schemas import (
    InterviewCreate,
    InterviewCreatedResponse,
    InterviewResponse,
    PlanResponse,
    ReportResponse,
)
from core_api.users.models import User

logger = logging.getLogger(__name__)

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

    interview = result.interview
    # Planning starts now (decision 052). If the job can't be sent, the plan
    # status read sends it again (decision 057), so creation still succeeds.
    try:
        voice_client.request_plan(
            interview_id=interview.id, repository_id=interview.repository_id
        )
    except voice_client.VoiceServiceError:
        logger.warning(
            "interview %d: plan job not sent; the status read will resend it",
            interview.id, exc_info=True,
        )

    base = InterviewResponse.model_validate(interview)
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

@router.get(
    "/{interview_id}/plan",
    response_model=PlanResponse,
    responses={
        404: {"description": "Interview not found"},
        503: {"description": "Voice Service unavailable"},
    },
)
def get_interview_plan(
    interview_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PlanResponse:
    """The question plan's status, polled by the live page (decision 052).

    If Voice Service has no plan for an interview that hasn't started, the
    job was lost: it is sent again here (lazy re-trigger, decision 057).
    """
    interview = _owned_interview(db, interview_id=interview_id, owner_user_id=current_user.id)
    try:
        plan = voice_client.get_plan_status(interview.id)
        if plan is None and interview.status == InterviewStatus.CREATED.value:
            voice_client.request_plan(
                interview_id=interview.id, repository_id=interview.repository_id
            )
            return PlanResponse(interview_id=interview.id, plan_status="generating")
    except voice_client.VoiceServiceError as exc:
        raise _plans_unavailable() from exc
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No plan")
    return PlanResponse(**plan)


@router.post(
    "/{interview_id}/plan/retry",
    response_model=PlanResponse,
    responses={
        404: {"description": "Interview not found"},
        409: {"description": "Interview has already started"},
        503: {"description": "Voice Service unavailable"},
    },
)
def retry_interview_plan(
    interview_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PlanResponse:
    """"Try again" after a failed plan (decision 052).

    Re-sends the job only for a missing or retryably failed plan. A plan
    that is generating or ready, or failed for good, is returned as is:
    re-sending would at best repeat work already under way.
    """
    interview = _owned_interview(db, interview_id=interview_id, owner_user_id=current_user.id)
    if interview.status != InterviewStatus.CREATED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Interview is '{interview.status}'; its plan can no longer change",
        )
    try:
        plan = voice_client.get_plan_status(interview.id)
        if plan is not None and not (plan["plan_status"] == "failed" and plan["retryable"]):
            return PlanResponse(**plan)
        voice_client.request_plan(
            interview_id=interview.id, repository_id=interview.repository_id
        )
    except voice_client.VoiceServiceError as exc:
        raise _plans_unavailable() from exc
    return PlanResponse(interview_id=interview.id, plan_status="generating")


def _plans_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Interview preparation is unavailable right now; try again shortly",
    )


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
    interview = _ended_interview(db, interview_id=interview_id, owner_user_id=current_user.id)

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


@router.post(
    "/{interview_id}/report/retry",
    response_model=ReportResponse,
    responses={
        202: {"model": ReportResponse, "description": "Report generation (re)started"},
        404: {"description": "Interview not found, or it has not ended"},
        503: {"description": "Evaluation Service unavailable"},
    },
)
def retry_interview_report(
    interview_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportResponse | JSONResponse:
    """Ask for a `failed` (or missing) report to be generated again.

    Reading a failed report doesn't regenerate it (decision 051), so the
    report page offers this instead. A ready or generating report is
    returned as is: under redelivery rules a second job for a generating
    report would generate it twice in parallel (decision 057). Otherwise
    the job is re-sent.
    """
    interview = _ended_interview(db, interview_id=interview_id, owner_user_id=current_user.id)

    try:
        report = evaluation_client.get_report(interview.id)
        if report is not None and report["status"] == "generating":
            return _generating(ReportResponse.model_validate(report))
        if report is not None and report["status"] == "ready":
            return ReportResponse.model_validate(report)
        evaluation_client.trigger_report(
            interview_id=interview.id,
            repository_id=interview.repository_id,
            outcome=interview.status,
        )
    except evaluation_client.EvaluationServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reports are unavailable right now; try again shortly",
        ) from exc

    return _generating(ReportResponse(interview_id=interview.id, status="generating"))


def _owned_interview(db: Session, *, interview_id: int, owner_user_id: int):
    """The user's interview. 404 for missing and not-yours alike, so
    ownership doesn't leak."""
    interview = service.get_interview_for_user(
        db, interview_id=interview_id, owner_user_id=owner_user_id
    )
    if interview is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    return interview


def _ended_interview(db: Session, *, interview_id: int, owner_user_id: int):
    """The user's interview, if it has ended. 404 otherwise."""
    interview = _owned_interview(db, interview_id=interview_id, owner_user_id=owner_user_id)
    if interview.status not in _ENDED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Interview is '{interview.status}'; reports exist once it has ended",
        )
    return interview
