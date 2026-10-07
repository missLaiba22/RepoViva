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
    database_url: str

    # LLM (decision 038). Passed to litellm explicitly: pydantic-settings
    # reads .env but does not export it to os.environ, where litellm
    # would otherwise look.
    groq_api_key: str
    llm_model: str = "groq/llama-3.3-70b-versatile"

    # Speech (decisions 043, 044). STT reuses groq_api_key.
    stt_model: str = "groq/whisper-large-v3-turbo"
    max_answer_seconds: int = 180
    deepgram_api_key: str
    tts_voice: str = "aura-2-thalia-en"

    # Interview shape
    max_questions: int = 6  # decision 041
    session_start_timeout_s: float = 10.0  # decision 035's consequence
    retrieval_top_k: int = 6  # decision 042


@lru_cache
def get_settings() -> Settings:
    return Settings()
