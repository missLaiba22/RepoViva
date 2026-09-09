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

    # Where Core API is reachable — used to POST status callbacks.
    core_api_base_url: str

    # Shared secret for HMAC signing on internal service-to-service calls.
    # Must match core-api's INTERNAL_HMAC_SECRET.
    internal_hmac_secret: str


@lru_cache
def get_settings() -> Settings:
    return Settings()