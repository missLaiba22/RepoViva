"""Internal endpoints, called only by other RepoViva services (decision 049).

Every request must carry a valid HMAC signature (decision 027); a failure
short-circuits with 401 before the handler runs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from repoviva_common.dependencies import hmac_dependency

from voice_service.config import get_settings
from voice_service.db import get_db_pool
from voice_service.session.turns import TurnStore

router = APIRouter(prefix="/internal/v1", tags=["internal"])


verify_hmac = hmac_dependency(lambda: get_settings().internal_hmac_secret)


@router.get(
    "/interviews/{interview_id}/turns",
    dependencies=[Depends(verify_hmac)],
    responses={401: {"description": "Missing or invalid HMAC signature"}},
)
async def list_turns(interview_id: int) -> dict:
    """The interview's turns, ordered by `seq`, for report generation.

    Always 200: an unknown interview and one with no turns yet look the
    same here, because interviews live in Core API (decision 040). The
    caller already knows the interview exists.
    """
    return {"turns": await TurnStore(get_db_pool()).list_turns(interview_id)}
