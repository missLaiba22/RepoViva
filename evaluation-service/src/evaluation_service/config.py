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


@lru_cache
def get_settings() -> Settings:
    return Settings()
