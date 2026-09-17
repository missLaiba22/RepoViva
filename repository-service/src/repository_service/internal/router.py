# repository-service/src/repository_service/internal/router.py
"""Internal API endpoints — called only by other RepoViva services.

All requests here must carry a valid HMAC signature (decision 027).
The signature is verified before the route handler runs; a failure
short-circuits the request with 401.
"""

import logging

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    status,
)
from pydantic import BaseModel, Field

from repository_service.config import Settings, get_settings
from repository_service.db import get_db_pool
from repository_service.indexing.embedder import EMBEDDER
from repository_service.ingestion.orchestrator import run_ingestion
from repository_service.internal.hmac_auth import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    HmacVerificationError,
    verify,
)
from repository_service.retrieval import search_chunks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/v1", tags=["internal"])


class IngestTriggerBody(BaseModel):
    github_url: str


class RetrieveRequestBody(BaseModel):
    query: str
    top_k: int = Field(default=10, ge=1, le=50)
    filename_prefix: str | None = None
    exclude_chunk_ids: list[int] = []


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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        ) from exc


@router.post(
    "/repositories/{repository_id}/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_hmac)],
)
async def ingest_trigger(
    repository_id: int,
    body: IngestTriggerBody,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Accept an ingest trigger from Core API and schedule the pipeline.

    Returns 202 immediately; the pipeline runs asynchronously via
    BackgroundTasks after the response is sent.
    """
    background_tasks.add_task(
        run_ingestion,
        repository_id=str(repository_id),
        github_url=body.github_url,
        workspace_root=settings.workspace_root,
    )
    return {"status": "accepted", "repository_id": str(repository_id)}


@router.post(
    "/repositories/{repository_id}/retrieve",
    dependencies=[Depends(verify_hmac)],
)
async def retrieve_chunks(
    repository_id: int,
    body: RetrieveRequestBody,
) -> dict:
    """Return the top-K code chunks most similar to `query`.

    Always 200, even with no matches (empty `chunks`) — this service has
    no local way to distinguish "unknown repo" from "ingestion still
    running" from "done" (that state lives in Core API), so it doesn't
    try; see decision on 404/409 handling.
    """
    try:
        query_embedding = await EMBEDDER.embed(body.query)
    except Exception as exc:
        logger.exception(
            "retrieval failed embedding query: repository_id=%s", repository_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="embedding upstream error",
        ) from exc

    chunks = await search_chunks(
        get_db_pool(),
        repository_id=str(repository_id),
        query_embedding=query_embedding,
        top_k=body.top_k,
        filename_prefix=body.filename_prefix,
        exclude_chunk_ids=body.exclude_chunk_ids,
    )
    return {"chunks": chunks}