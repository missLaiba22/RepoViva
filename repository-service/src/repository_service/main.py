from contextlib import asynccontextmanager

from fastapi import FastAPI
from repoviva_common.http import close_async_client, open_async_client
from repoviva_common.request_id import RequestIDMiddleware, configure_logging

from repository_service.config import export_provider_keys, get_settings
from repository_service.db import apply_schema, close_pool, init_pool
from repository_service.internal.router import router as internal_router

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    export_provider_keys(get_settings())
    await init_pool()
    open_async_client()
    await apply_schema()
    try:
        yield
    finally:
        await close_async_client()
        await close_pool()


app = FastAPI(
    title="RepoViva Repository Service",
    description="Owns repository ingestion and retrieval.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(RequestIDMiddleware)

app.include_router(internal_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. No auth, no dependencies."""
    return {"status": "ok"}