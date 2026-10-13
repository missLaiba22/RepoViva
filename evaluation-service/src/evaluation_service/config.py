from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # → evaluation-service/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str
    voice_service_base_url: str
    repository_service_base_url: str
    internal_hmac_secret: str
    database_url: str

    # Grading LLM (decision 051). Passed to litellm explicitly: pydantic-settings
    # reads .env but does not export it to os.environ, where litellm would
    # otherwise look.
    groq_api_key: str
    eval_llm_model: str = "groq/openai/gpt-oss-120b"

    # SQS (decision 057). Endpoint and keys are set only for LocalStack;
    # on AWS they stay unset and the task's IAM role is used.
    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    interview_events_queue_url: str
    report_jobs_queue_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
