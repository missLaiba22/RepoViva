# core-api/src/core_api/internal/router.py
"""Internal API endpoints — called only by other RepoViva services.

All requests here carry an HMAC signature (decision 027) verified by
`verify_hmac` before the handler runs. Failing signatures short-circuit
with 401.
"""

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from repoviva_common.dependencies import hmac_dependency
from sqlalchemy.orm import Session

from core_api.config import get_settings
from core_api.db import get_db
from core_api.internal.schemas import (
    SessionTokenConsumeBody,
    SessionTokenConsumeResponse,
)
from core_api.interviews import service as interviews_service

router = APIRouter(prefix="/internal/v1", tags=["internal"])


verify_hmac = hmac_dependency(lambda: get_settings().internal_hmac_secret)


@router.post(
    "/session-tokens/consume",
    response_model=SessionTokenConsumeResponse,
    dependencies=[Depends(verify_hmac)],
    responses={
        401: {"description": "Missing or invalid HMAC signature"},
        403: {"description": "Token unknown, expired, or already consumed"},
    },
)
def consume_session_token(
    body: SessionTokenConsumeBody,
    db: Session = Depends(get_db),
) -> SessionTokenConsumeResponse | JSONResponse:
    """Exchange a one-time session token for the interview it belongs to.

    Called once per session by Voice Service on `session.start`. Not
    idempotent — a second call with the same token gets 403 `consumed`.
    """
    try:
        consumed = interviews_service.consume_session_token(db, raw_token=body.token)
    except interviews_service.TokenRejectedError as exc:
        # JSONResponse, not HTTPException: HTTPException would wrap the
        # body as {"detail": ...}, but decision 035's contract is {reason}.
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"reason": exc.reason},
        )

    return SessionTokenConsumeResponse(**consumed._asdict())