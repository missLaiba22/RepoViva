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
    Query,
    status,
)
from pydantic import BaseModel, Field
from repoviva_common.dependencies import hmac_dependency

from repository_service.config import Settings, get_settings
from repository_service.db import get_db_pool
from repository_service.indexing.embedder import EMBEDDER
from repository_service.ingestion.orchestrator import run_ingestion
from repository_service.retrieval import get_chunks_by_ids, list_areas, search_chunks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/v1", tags=["internal"])


class IngestTriggerBody(BaseModel):
    github_url: str


class RetrieveRequestBody(BaseModel):
    query: str
    top_k: int = Field(default=10, ge=1, le=50)
    filename_prefix: str | None = None
    exclude_chunk_ids: list[int] = []


class ChunksByIdBody(BaseModel):
    # A report covers about six turns of six chunks each; 200 leaves room
    # without letting one call pull a whole repository.
    ids: list[int] = Field(min_length=1, max_length=200)


class AreaOut(BaseModel):
    path: str
    chunk_count: int


class AreasResponse(BaseModel):
    areas: list[AreaOut]


verify_hmac = hmac_dependency(lambda: get_settings().internal_hmac_secret)


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


@router.post(
    "/repositories/{repository_id}/chunks",
    dependencies=[Depends(verify_hmac)],
)
async def get_chunks(
    repository_id: int,
    body: ChunksByIdBody,
) -> dict:
    """Return the chunks with the given ids, for Evaluation Service (decision 049).

    Always 200. Ids with no row are left out rather than failing the call,
    the same way /retrieve returns an empty list for an unknown repository.
    No `similarity`: these chunks weren't ranked against a query.
    """
    chunks = await get_chunks_by_ids(
        get_db_pool(),
        repository_id=str(repository_id),
        ids=body.ids,
    )
    return {"chunks": chunks}


@router.get(
    "/repositories/{repository_id}/areas",
    response_model=AreasResponse,
    dependencies=[Depends(verify_hmac)],
)
async def get_areas(
    repository_id: int,
    limit: int = Query(ge=1, le=50),
) -> AreasResponse:
    """The repository's `limit` largest areas, for question planning (decision 052).

    Always 200: no chunks gives an empty list, as /retrieve does.
    """
    areas = await list_areas(get_db_pool(), repository_id=str(repository_id), limit=limit)
    return AreasResponse(
        areas=[AreaOut(path=a.path, chunk_count=a.chunk_count) for a in areas]
    )
