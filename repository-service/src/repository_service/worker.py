"""Repository Service worker: consumes ingestion jobs from SQS (decision 057).

Run with `python -m repository_service.worker`, from the same image as the API.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from pydantic import BaseModel
from repoviva_common.http import close_async_client, open_async_client
from repoviva_common.messaging import Message, close_messaging, open_messaging, run_worker
from repoviva_common.request_id import configure_logging

from repository_service.config import export_provider_keys, get_settings
from repository_service.db import apply_schema, close_pool, get_db_pool, init_pool
from repository_service.ingestion import jobs
from repository_service.ingestion.orchestrator import run_ingestion

logger = logging.getLogger(__name__)


class IngestionRequested(BaseModel):
    """`data` of an `ingestion.requested` job, sent by Core API."""

    repository_id: int
    github_url: str


async def handle_ingestion_job(message: Message) -> None:
    job = IngestionRequested.model_validate(message.data)
    repository_id = str(job.repository_id)
    await jobs.claim(get_db_pool(), repository_id=repository_id, github_url=job.github_url)
    await run_ingestion(repository_id)


async def main() -> None:
    settings = get_settings()
    export_provider_keys(settings)
    await init_pool()
    await apply_schema()
    open_async_client()
    open_messaging(
        region=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url,
        access_key_id=settings.aws_access_key_id,
        secret_access_key=settings.aws_secret_access_key,
    )

    stop = asyncio.Event()
    # SIGTERM is how ECS stops a task; not supported by the event loop on Windows.
    with contextlib.suppress(NotImplementedError):
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop.set)

    logger.info("worker started: queue=%s", settings.ingestion_jobs_queue_url)
    try:
        await run_worker({settings.ingestion_jobs_queue_url: handle_ingestion_job}, stop=stop)
    finally:
        close_messaging()
        await close_async_client()
        await close_pool()


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
