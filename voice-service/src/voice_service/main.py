import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from repoviva_common.http import close_async_client, open_async_client
from repoviva_common.messaging import close_messaging, open_messaging

from voice_service.config import get_settings
from voice_service.db import close_db, ensure_indexes, init_db
from voice_service.internal.router import router as internal_router
from voice_service.ws import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db()
    open_async_client()
    open_messaging(
        region=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url,
        access_key_id=settings.aws_access_key_id,
        secret_access_key=settings.aws_secret_access_key,
    )
    await ensure_indexes()
    try:
        yield
    finally:
        close_messaging()
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
