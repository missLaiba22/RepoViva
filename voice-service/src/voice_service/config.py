from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # → voice-service/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str
    core_api_base_url: str
    repository_service_base_url: str
    internal_hmac_secret: str

    # SQS and EventBridge (decision 057). Endpoint and keys are set only for
    # LocalStack; on AWS they stay unset and the task's IAM role is used.
    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    event_bus_name: str = "repoviva"
    planning_jobs_queue_url: str

    # Interview sessions (decision 053)
    mongodb_uri: str
    mongodb_database: str = "repoviva_voice"

    # LLM (decisions 038, 046). Passed to litellm explicitly: pydantic-settings
    # reads .env but does not export it to os.environ, where litellm
    # would otherwise look.
    groq_api_key: str
    llm_model: str = "groq/qwen/qwen3.8-27b"

    # Speech (decisions 043, 044). STT reuses groq_api_key.
    stt_model: str = "groq/whisper-large-v3-turbo"
    max_answer_seconds: int = 180
    deepgram_api_key: str
    tts_voice: str = "aura-2-thalia-en"

    # Interview shape
    max_questions: int = 6  # decision 041: one planned question per area (052)
    session_start_timeout_s: float = 10.0  # decision 035's consequence
    # Core API's ACTIVE_SESSION_CUTOFF_SECONDS must exceed this (decision 059).
    max_session_seconds: int = 1800
    plan_chunks_per_area: int = 2  # decision 052: sized for Groq's per-minute tokens


@lru_cache
def get_settings() -> Settings:
    return Settings()
