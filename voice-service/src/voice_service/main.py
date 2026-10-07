import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from voice_service.db import apply_schema, close_pool, init_pool
from voice_service.internal.router import router as internal_router
from voice_service.ws import router as ws_router

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
    title="RepoViva Voice Service",
    description="Runs the live interview session.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(ws_router)
app.include_router(internal_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. No auth, no dependencies."""
    return {"status": "ok"}
