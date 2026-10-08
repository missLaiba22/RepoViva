import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from evaluation_service.db import apply_schema, close_pool, init_pool
from evaluation_service.generation import resume_generating
from evaluation_service.internal.router import router as internal_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    await apply_schema()
    # Startup resume (decision 049): reports left `generating` by a crash
    # or reload. In the background, so the service answers while it runs.
    resume = asyncio.create_task(resume_generating())
    try:
        yield
    finally:
        # A report cut off here stays `generating` and resumes next boot.
        resume.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await resume
        await close_pool()


app = FastAPI(
    title="RepoViva Evaluation Service",
    description="Grades a finished interview and writes its report.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(internal_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. No auth, no dependencies."""
    return {"status": "ok"}
