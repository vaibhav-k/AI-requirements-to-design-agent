"""Runtime configuration for the web API layer.

Everything else in this project (the CLI, the MCP server, ``ArtifactStore``)
reads configuration straight from environment variables via ``os.getenv`` at
import time. The web layer introduced alongside Entra ID authentication needs
a bit more than that — a cached ``Settings`` singleton that FastAPI
dependencies (``require_user`` in particular) can pull from on every request
without re-reading the environment — so it gets its own small
``pydantic-settings`` model instead of bolting onto the existing pattern.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- HTTP host ----
    host: str = "0.0.0.0"
    port: int = 8000
    cors_allow_origins: str = "http://localhost:5173,http://localhost:4173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    # ---- Authentication ----
    # Authentication is opt-in: local development keeps working
    # unauthenticated unless explicitly enabled.
    auth_enabled: bool = False
    entra_tenant_id: str = ""
    entra_client_id: str = ""
    entra_api_scope: str = "access_as_user"

    # ---- Cosmos DB (web API session state) ----
    # Backs app/infrastructure/session_store.py. The CLI has no equivalent —
    # its session state lives only in the running process — so these are only
    # required to run the web API's requirements/architecture endpoints.
    cosmos_endpoint: str = ""
    cosmos_key: str = ""
    cosmos_database: str = "requirements-to-design"
    cosmos_sessions_container: str = "sessions"
    cosmos_auth_mode: str = "key"  # "key" | "managed_identity"


@lru_cache
def get_settings() -> Settings:
    return Settings()
