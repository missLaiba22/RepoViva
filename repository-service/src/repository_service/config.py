# repository-service/src/repository_service/config.py
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # → repository-service/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str
    core_api_base_url: str
    internal_hmac_secret: str

    # Where cloned repositories live on disk during and after ingestion.
    # One subdirectory per repository, keyed by repository_id.
    # Persists across service restarts — the clone is scratch space for
    # the ingestion pipeline, but keeping it around makes re-ingestion cheap.
    workspace_root: Path


@lru_cache
def get_settings() -> Settings:
    return Settings()