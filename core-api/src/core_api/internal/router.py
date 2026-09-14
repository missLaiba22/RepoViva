# core-api/src/core_api/internal/router.py
"""Internal API endpoints — called only by other RepoViva services.

All requests here carry an HMAC signature (decision 027) verified by
`verify_hmac` before the handler runs. Failing signatures short-circuit
with 401.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from core_api.config import get_settings
from core_api.db import get_db
from core_api.internal.schemas import IngestionEventBody
from core_api.repositories import service as repositories_service
from core_api.repositories.service import IllegalTransitionError
from core_api.security.hmac_auth import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    HmacVerificationError,
    verify,
)

router = APIRouter(prefix="/internal/v1", tags=["internal"])


async def verify_hmac(request: Request) -> None:
    """FastAPI dependency: verify HMAC signature on inbound internal requests.

    Reads the raw body bytes — the signature covers exactly what was sent,
    not what Pydantic parses later. `await request.body()` caches the bytes,
    so the route handler still sees the parsed model.
    """
    body = await request.body()
    settings = get_settings()
    try:
        verify(
            body=body,
            timestamp_header=request.headers.get(TIMESTAMP_HEADER),
            signature_header=request.headers.get(SIGNATURE_HEADER),
            secret=settings.internal_hmac_secret,
        )
    except HmacVerificationError as exc:
        # Specific reason logged server-side; caller gets a generic 401
        # (mirrors the discipline in repository-service).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        ) from exc


@router.post(
    "/repositories/{repository_id}/events",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_hmac)],
    responses={
        401: {"description": "Missing or invalid HMAC signature"},
        404: {"description": "Repository not found"},
        422: {"description": "Illegal state transition for current status"},
    },
)
def receive_ingestion_event(
    repository_id: int,
    body: IngestionEventBody,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Receive an ingestion status event from Repository Service.

    Deduplication by event_id is deferred for MVP — see slice 3 close-out
    of decision 028. Event ordering is defended against by a loose state
    machine in the service layer (see repositories/service.py).
    """
    error_message: str | None = None
    if body.event_type == "ingestion.failed" and body.data is not None:
        val = body.data.get("error_message")
        if isinstance(val, str):
            error_message = val

    try:
        repo = repositories_service.apply_ingestion_event(
            db,
            repository_id=repository_id,
            event_type=body.event_type,
            error_message=error_message,
        )
    except IllegalTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    return {"status": "accepted", "repository_id": str(repository_id)}