"""Build a CocoIndex App for one repository's ingestion."""

from pathlib import Path
from typing import AsyncIterator

import asyncpg
import cocoindex as coco

from repository_service.indexing.config import PG_DB
from repository_service.indexing.flow import app_main


def build_app(
    repository_id: str,
    commit_sha: str,
    source_dir: Path,
    pool: asyncpg.Pool,
) -> coco.App:
    """One App per repo. Pool is shared — not owned by this App."""

    @coco.lifespan
    async def lifespan(
        builder: coco.EnvironmentBuilder,
    ) -> AsyncIterator[None]:
        # No `async with` — FastAPI owns the pool lifecycle.
        builder.provide(PG_DB, pool)
        yield

    return coco.App(
        coco.AppConfig(name=f"repoviva-{repository_id}"),
        app_main,
        sourcedir=str(source_dir),
        repository_id=repository_id,
        commit_sha=commit_sha,
    )