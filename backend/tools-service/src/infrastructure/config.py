"""Runtime configuration for tools-service.

Mirrors Parnell-AI-Persona-Agent's ``backend/tools-service/src/infrastructure
/config.py`` shape: a small cached ``pydantic-settings`` model, no
``AZURE_OPENAI_*``/Cosmos/Blob settings at all - this service never calls
an LLM and never holds state, so it has nothing to read beyond its own
bind address.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TOOLS_SERVICE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"  # nosec B104 -- intentional for containerized deployment
    port: int = 8100
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
