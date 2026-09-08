from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from core_api.config import get_settings
from core_api.db import get_db

app = FastAPI(title="RepoViva Core API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "reachable"}