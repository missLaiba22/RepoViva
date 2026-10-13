# repository-service/src/repository_service/config.py
import os
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # → repository-service/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str
    internal_hmac_secret: str

    # Where cloned repositories live on disk during and after ingestion.
    # One subdirectory per repository, keyed by repository_id.
    # Persists across service restarts — the clone is scratch space for
    # the ingestion pipeline, but keeping it around makes re-ingestion cheap.
    workspace_root: Path
    database_url: str
    voyage_api_key: SecretStr

    # SQS and EventBridge (decision 057). Endpoint and keys are set only for LocalStack;
    # on AWS they stay unset and the task's IAM role is used.
    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    ingestion_jobs_queue_url: str
    event_bus_name: str = "repoviva"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def export_provider_keys(settings: Settings) -> None:
    """Put API keys where litellm reads them: the process env, at call time."""
    os.environ["VOYAGE_API_KEY"] = settings.voyage_api_key.get_secret_value()