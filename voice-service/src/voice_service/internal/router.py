"""Internal endpoints, called only by other RepoViva services (decisions 049, 052).

Every request must carry a valid HMAC signature (decision 027); a failure
short-circuits with 401 before the handler runs.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from repoviva_common.dependencies import hmac_dependency

from voice_service.config import get_settings
from voice_service.db import get_db
from voice_service.planning.job import run_planning
from voice_service.session.store import PlanStatus, SessionStore

router = APIRouter(prefix="/internal/v1", tags=["internal"])


class PlanTriggerBody(BaseModel):
    repository_id: int


class PlanTriggerResponse(BaseModel):
    interview_id: int
    plan_status: PlanStatus
    scheduled: bool


class PlanStatusResponse(BaseModel):
    interview_id: int
    plan_status: PlanStatus
    error_message: str | None
    # Only meaningful when `failed`: false means retrying can't help.
    retryable: bool | None


class Turn(BaseModel):
    seq: int
    question_text: str
    answer_text: str | None
    status: str
    retrieved_chunk_ids: list[int]


class TurnsResponse(BaseModel):
    turns: list[Turn]


verify_hmac = hmac_dependency(lambda: get_settings().internal_hmac_secret)


@router.post(
    "/interviews/{interview_id}/plan",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PlanTriggerResponse,
    dependencies=[Depends(verify_hmac)],
    responses={401: {"description": "Missing or invalid HMAC signature"}},
)
async def trigger_plan(
    interview_id: int, body: PlanTriggerBody, background_tasks: BackgroundTasks
) -> PlanTriggerResponse:
    """Start planning the interview's questions, unless it is already under way.

    Always 202. A new or `failed` plan is claimed and written in the
    background; one that is `generating` or `ready` is left alone.
    `scheduled` says which happened.
    """
    store = SessionStore(get_db())
    scheduled = await store.claim_plan(
        interview_id=interview_id, repository_id=body.repository_id
    )
    if scheduled:
        background_tasks.add_task(run_planning, interview_id)
        plan_status = "generating"
    else:
        plan_status = (await store.get_plan_state(interview_id)).plan_status
    return PlanTriggerResponse(
        interview_id=interview_id, plan_status=plan_status, scheduled=scheduled
    )


@router.get(
    "/interviews/{interview_id}/plan",
    response_model=PlanStatusResponse,
    dependencies=[Depends(verify_hmac)],
    responses={
        401: {"description": "Missing or invalid HMAC signature"},
        404: {"description": "Planning was never triggered for this interview"},
    },
)
async def get_plan_status(interview_id: int) -> PlanStatusResponse:
    """The plan's status, for Core API to pass to the live page. Never the questions."""
    plan = await SessionStore(get_db()).get_plan_state(interview_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
    return PlanStatusResponse(interview_id=interview_id, **plan.model_dump())


@router.get(
    "/interviews/{interview_id}/turns",
    response_model=TurnsResponse,
    dependencies=[Depends(verify_hmac)],
    responses={401: {"description": "Missing or invalid HMAC signature"}},
)
async def list_turns(interview_id: int) -> TurnsResponse:
    """The interview's asked questions, ordered by `seq`, for report generation.

    Always 200: an unknown interview and one with no questions asked yet
    look the same here, because interviews live in Core API (decision 040).
    The caller already knows the interview exists.
    """
    turns = await SessionStore(get_db()).list_turns(interview_id)
    return TurnsResponse(turns=[Turn(**t) for t in turns])
