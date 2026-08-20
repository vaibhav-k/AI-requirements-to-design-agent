"""Runtime configuration for the design-tools MCP wrapper.

Mirrors Parnell-AI-Persona-Agent's per-capability wrapper config shape
(e.g. ``backend/mcp-wrapper/src/architecture_design_wrapper/infrastructure
/config.py``) - a small cached settings model naming this wrapper's own
bind address/path plus where to reach tools-service.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DESIGN_TOOLS_WRAPPER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8210
    path: str = "/mcp/design-tools"

    tools_service_base_url: str = "http://localhost:8100"
    tools_service_timeout: float = 60.0

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
