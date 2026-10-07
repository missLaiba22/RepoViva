import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from evaluation_service.db import apply_schema, close_pool, init_pool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    await apply_schema()
    try:
        yield
    finally:
        await close_pool()


app = FastAPI(
    title="RepoViva Evaluation Service",
    description="Grades a finished interview and writes its report.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. No auth, no dependencies."""
    return {"status": "ok"}
