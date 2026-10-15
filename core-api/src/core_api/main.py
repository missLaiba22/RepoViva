from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from repoviva_common.http import close_sync_client, open_sync_client
from repoviva_common.messaging import close_messaging, open_messaging
from repoviva_common.request_id import RequestIDMiddleware, configure_logging
from sqlalchemy import text
from sqlalchemy.orm import Session

from core_api.auth.router import router as auth_router
from core_api.config import get_settings
from core_api.db import get_db
from core_api.internal.router import router as internal_router
from core_api.interviews.router import router as interviews_router
from core_api.repositories.router import router as repositories_router
from core_api.users.router import router as users_router

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    open_sync_client()
    open_messaging(
        region=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url,
        access_key_id=settings.aws_access_key_id,
        secret_access_key=settings.aws_secret_access_key,
    )
    try:
        yield
    finally:
        close_messaging()
        close_sync_client()


app = FastAPI(title="RepoViva Core API", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestIDMiddleware)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(repositories_router)
app.include_router(internal_router)
app.include_router(interviews_router)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "reachable"}