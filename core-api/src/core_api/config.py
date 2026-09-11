from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # → core-api/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core
    database_url: str
    env: str

    # GitHub OAuth
    github_client_id: str
    github_client_secret: str
    github_oauth_redirect_uri: str

    # Secrets
    cookie_secret: str
    token_encryption_key: str

    # Where Repository Service lives — used to fire the ingest trigger.
    repository_service_base_url: str

    # Shared HMAC secret for signing internal service-to-service calls.
    # Must match repository-service's INTERNAL_HMAC_SECRET.
    internal_hmac_secret: str


@lru_cache
def get_settings() -> Settings:
    return Settings()