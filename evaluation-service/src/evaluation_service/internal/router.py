"""Internal endpoints, called only by Core API (decision 049).

Every request must carry a valid HMAC signature (decision 027); a failure
short-circuits with 401 before the handler runs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from repoviva_common.dependencies import hmac_dependency

from evaluation_service.config import get_settings
from evaluation_service.db import get_db_pool
from evaluation_service.reports import ReportStore

router = APIRouter(prefix="/internal/v1", tags=["internal"])


verify_hmac = hmac_dependency(lambda: get_settings().internal_hmac_secret)


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
