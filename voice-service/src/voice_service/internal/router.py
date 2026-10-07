"""Internal endpoints, called only by other RepoViva services (decision 049).

Every request must carry a valid HMAC signature (decision 027); a failure
short-circuits with 401 before the handler runs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from voice_service.config import get_settings
from voice_service.db import get_db_pool
from voice_service.internal.hmac_auth import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    HmacVerificationError,
    verify,
)
from voice_service.session.turns import TurnStore

router = APIRouter(prefix="/internal/v1", tags=["internal"])


async def verify_hmac(request: Request) -> None:
    """FastAPI dependency: 401 unless the request is signed with the shared secret."""
    try:
        verify(
            body=await request.body(),
            timestamp_header=request.headers.get(TIMESTAMP_HEADER),
            signature_header=request.headers.get(SIGNATURE_HEADER),
            secret=get_settings().internal_hmac_secret,
        )
    except HmacVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized") from exc


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
