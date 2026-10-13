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
    # Where the browser goes after login: the frontend's /home. Its host
    # must match GITHUB_OAUTH_REDIRECT_URI's (localhost), or the session
    # cookie set on the callback won't reach the frontend.
    frontend_base_url: str = "http://localhost:5173"

    # Secrets
    cookie_secret: str
    token_encryption_key: str

    # SQS (decision 057). Endpoint and keys are set only for LocalStack;
    # on AWS they stay unset and the task's IAM role is used.
    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    ingestion_jobs_queue_url: str
    report_jobs_queue_url: str
    planning_jobs_queue_url: str
    # Where the worker receives Voice Service's interview.ended and
    # Repository Service's ingestion.* events.
    interview_events_queue_url: str
    ingestion_events_queue_url: str

    # Where Voice Service lives — question plan status (decision 052).
    voice_service_base_url: str
    # Where Evaluation Service lives — report trigger and reads (decision 049).
    evaluation_service_base_url: str

    # Shared HMAC secret for signing internal service-to-service calls.
    # Must match repository-service's INTERNAL_HMAC_SECRET.
    internal_hmac_secret: str
    # How long a newly issued interview session token stays valid if
    # unused (decision 035). An interview rule, so it lives in config,
    # not in security/session_tokens.py.
    session_token_ttl_minutes: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()