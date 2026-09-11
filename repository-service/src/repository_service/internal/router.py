"""Internal API endpoints — called only by other RepoViva services.

All requests here must carry a valid HMAC signature (decision 027).
The signature is verified before the route handler runs; a failure
short-circuits the request with 401.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from repository_service.config import get_settings
from repository_service.internal.hmac_auth import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    HmacVerificationError,
    verify,
)

router = APIRouter(prefix="/internal/v1", tags=["internal"])


class IngestTriggerBody(BaseModel):
    github_url: str


async def verify_hmac(request: Request) -> None:
    """FastAPI dependency: verify the HMAC signature on an inbound request.

    Reads the raw body bytes (not the parsed JSON) — the signature covers
    exactly what was sent on the wire, not what Pydantic parses out of it.
    Raises HTTPException(401) on any verification failure.

    Note: `await request.body()` caches the bytes, so the route handler
    can still parse the body into its Pydantic model afterwards.
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
        # Log the specific reason server-side; return a generic 401 to the caller.
        # (Not leaking the reason back to the caller is deliberate — see hmac_auth.py.)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        ) from exc


@router.post(
    "/repositories/{repository_id}/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_hmac)],
)
def ingest_trigger(repository_id: int, body: IngestTriggerBody) -> dict[str, str]:
    """Accept an ingest trigger from Core API.

    Currently does nothing with the request — real ingestion is deferred
    (see decision 028). The 202 response acknowledges receipt; when real
    ingestion is implemented, the actual work will run asynchronously and
    this endpoint will still return 202 immediately.
    """
    # TODO(slice-3): kick off real ingestion for `repository_id` from `body.github_url`.
    return {"status": "accepted", "repository_id": str(repository_id)}