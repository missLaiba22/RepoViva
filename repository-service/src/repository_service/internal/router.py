# """Internal API router. HMAC-authenticated; called by core-api only."""

# from __future__ import annotations

# from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

# from repository_service.config import get_settings
# from repository_service.ingestion.fake_job import run_fake_ingestion
# from repository_service.internal.core_api_client import get_core_api_client
# from repository_service.internal.hmac_auth import (
#     SIGNATURE_HEADER,
#     TIMESTAMP_HEADER,
#     SignatureError,
#     verify,
# )

# router = APIRouter(prefix="/internal/v1", tags=["internal"])


# async def require_hmac(request: Request) -> None:
#     """FastAPI dependency: reject the request unless it carries a valid signature.

#     Reading ``request.body()`` here is safe — Starlette caches it, so the route
#     handler can still read the same body afterwards.
#     """
#     settings = get_settings()
#     body = await request.body()
#     try:
#         verify(
#             settings.internal_hmac_secret,
#             body,
#             timestamp=request.headers.get(TIMESTAMP_HEADER),
#             signature=request.headers.get(SIGNATURE_HEADER),
#             max_skew_seconds=settings.internal_hmac_max_skew_seconds,
#         )
#     except SignatureError as exc:
#         raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc


# @router.post(
#     "/repositories/{repository_id}/ingest",
#     status_code=status.HTTP_202_ACCEPTED,
#     dependencies=[Depends(require_hmac)],
# )
# async def trigger_ingest(repository_id: str, background: BackgroundTasks) -> dict[str, str]:
#     """Kick off an (async, fire-and-forget) ingestion job for the repository."""
#     background.add_task(run_fake_ingestion, repository_id, get_core_api_client())
#     return {"status": "accepted", "repository_id": repository_id}
