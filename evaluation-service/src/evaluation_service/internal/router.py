"""Internal endpoints, called only by Core API (decision 049).

Every request must carry a valid HMAC signature (decision 027); a failure
short-circuits with 401 before the handler runs.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel

from evaluation_service.config import get_settings
from evaluation_service.db import get_db_pool
from evaluation_service.generation import run_generation
from evaluation_service.internal.hmac_auth import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    HmacVerificationError,
    verify,
)
from evaluation_service.reports import PendingReport, ReportStore

router = APIRouter(prefix="/internal/v1", tags=["internal"])


class ReportTriggerBody(BaseModel):
    interview_id: int
    repository_id: int
    outcome: Literal["completed", "interrupted"]


async def verify_hmac(request: Request) -> None:
    """FastAPI dependency: 401 unless the request is signed with the shared secret.

    Reads the raw body bytes; FastAPI caches them, so the handler can still
    parse the body afterwards.
    """
    try:
        verify(
            body=await request.body(),
            timestamp_header=request.headers.get(TIMESTAMP_HEADER),
            signature_header=request.headers.get(SIGNATURE_HEADER),
            secret=get_settings().internal_hmac_secret,
        )
    except HmacVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized") from exc


@router.post(
    "/reports",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_hmac)],
    responses={401: {"description": "Missing or invalid HMAC signature"}},
)
async def trigger_report(body: ReportTriggerBody, background_tasks: BackgroundTasks) -> dict:
    """Start generating the interview's report, unless it is already under way.

    Always 202. A new or `failed` report is claimed and generated in the
    background; one that is `generating` or `ready` is left alone
    (decision 049). `scheduled` says which happened.
    """
    store = ReportStore(get_db_pool())
    report = PendingReport(
        interview_id=body.interview_id,
        repository_id=body.repository_id,
        # An interrupted interview still gets a report, marked partial (decision 008).
        partial=body.outcome == "interrupted",
    )
    scheduled = await store.claim(
        interview_id=report.interview_id,
        repository_id=report.repository_id,
        partial=report.partial,
    )
    if scheduled:
        background_tasks.add_task(run_generation, report)
        report_status = "generating"
    else:
        report_status = await store.get_status(report.interview_id)
    return {"interview_id": report.interview_id, "status": report_status, "scheduled": scheduled}


@router.get(
    "/reports/{interview_id}",
    dependencies=[Depends(verify_hmac)],
    responses={
        401: {"description": "Missing or invalid HMAC signature"},
        404: {"description": "No report for this interview"},
    },
)
async def get_report(interview_id: int) -> dict:
    """The report in whatever state it is in.

    While `generating`, the content fields are null. Core API turns that
    into 202 for the frontend, and a 404 here into a lazy re-trigger.
    """
    report = await ReportStore(get_db_pool()).get(interview_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report not found")
    return report
