import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from repoviva_common.http import close_async_client, open_async_client

from evaluation_service.db import apply_schema, close_pool, init_pool
from evaluation_service.internal.router import router as internal_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    open_async_client()
    await apply_schema()
    try:
        yield
    finally:
        await close_async_client()
        await close_pool()


app = FastAPI(
    title="RepoViva Evaluation Service",
    description="Serves interview reports; the worker grades interviews and writes them.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(internal_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. No auth, no dependencies."""
    return {"status": "ok"}
