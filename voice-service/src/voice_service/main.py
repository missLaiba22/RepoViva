import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from repoviva_common.http import close_async_client, open_async_client

from voice_service.db import close_db, ensure_indexes, init_db
from voice_service.internal.router import router as internal_router
from voice_service.planning.job import resume_planning
from voice_service.ws import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    open_async_client()
    await ensure_indexes()
    # Startup resume: plans left `generating` by a crash or reload. In the
    # background, so the service answers while it runs.
    resume = asyncio.create_task(resume_planning())
    try:
        yield
    finally:
        # A plan cut off here stays `generating` and resumes next boot.
        resume.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await resume
        await close_async_client()
        await close_db()


app = FastAPI(
    title="RepoViva Voice Service",
    description="Plans the interview's questions and runs the live session.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(ws_router)
app.include_router(internal_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. No auth, no dependencies."""
    return {"status": "ok"}
