import json
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str

    # PostgreSQL with pgvector
    database_url: str

    # Session - inactivity-based expiration
    session_inactivity_minutes: int = 5  # Sessions expire after 5 min of inactivity
    cleanup_interval_minutes: int = 1    # Check for expired sessions every 1 min

    # CORS - accepts JSON array or comma-separated origins via CORS_ORIGINS env var
    cors_origins: list[str] = ["http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> list[str]:
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # File upload
    max_file_size_mb: int = 10

    # Rate limiting (showcase protection)
    max_queries_per_session: int = 5
    max_documents_per_session: int = 3
    max_sessions_per_minute: int = 10

    # AI models
    processor_model: str = "gpt-4.1-mini"
    tts_model: str = "gpt-4o-mini-tts"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
