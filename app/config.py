from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = "gemini"  # gemini | groq | openai | anthropic | mock
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    database_url: str = "sqlite+aiosqlite:///./ride_chatbot.db"
    trip_simulator_interval_sec: float = 5.0

    # Demand surge: count of active trips above this adds extra multiplier step
    demand_surge_threshold: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
