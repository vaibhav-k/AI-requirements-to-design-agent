"""FastAPI application entry point.

Run with:

    python -m app.web.main

or, for auto-reload during development:

    uvicorn app.web.main:app --reload

Authentication is opt-in (see ``app/config.py``). With ``AUTH_ENABLED=false``
(the default) every route is reachable without a token, matching the
project's existing "local dev just works" philosophy. Set ``AUTH_ENABLED=true``
plus ``ENTRA_TENANT_ID`` / ``ENTRA_CLIENT_ID`` to require a valid Entra ID
bearer token on every request handled by a router registered with
``dependencies=[Depends(require_user)]`` — see ``create_app`` below.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.requirements import router as requirements_router
from app.config import get_settings
from app.infrastructure.session_store import CosmosSessionStore
from app.security.auth import current_claims, principal_of, require_user
from app.storage import AZURE_CONNECTION_STRING, AZURE_CONTAINER, ArtifactStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Construct the Cosmos session store and Blob artifact store once, at startup.

    Both are synchronous clients (see ``app/infrastructure/session_store.py``
    for why), so building them here — rather than lazily per-request — keeps
    the cost of the ``create_database_if_not_exists``/``create_container_if_not_exists``
    round-trip out of the request path.
    """
    session_store = CosmosSessionStore()
    session_store.start()
    app.state.session_store = session_store

    artifact_store = ArtifactStore(
        connection_string=AZURE_CONNECTION_STRING,
        container_name=AZURE_CONTAINER,
    )
    app.state.artifact_store = artifact_store

    try:
        yield
    finally:
        # Each store's close() is independent — one raising must not stop the
        # other from closing, and must not turn a normal shutdown (Ctrl+C,
        # SIGTERM, --reload restarting) into "Application shutdown failed."
        # the way an unguarded call did before (see the CosmosClient fix in
        # session_store.close()'s docstring).
        for name, close in (
            ("session_store", session_store.close),
            ("artifact_store", artifact_store.close),
        ):
            try:
                close()
            except Exception:
                logger.warning("Error closing %s during shutdown", name, exc_info=True)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AI Requirements → System Design Agent",
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        """Unauthenticated liveness probe."""
        return {"status": "ok"}

    @app.get("/me", tags=["auth"], dependencies=[Depends(require_user)])
    async def whoami(request: Request) -> dict[str, str | bool]:
        """Returns the caller's identity, proving the auth wiring works.

        With ``AUTH_ENABLED=false`` this returns an empty/anonymous identity
        rather than 401ing, since ``require_user`` is a no-op in that mode —
        same behavior as every other route until real endpoints are added.
        """
        claims = current_claims(request)
        return {
            "authenticated": bool(claims),
            "principal": principal_of(claims) if claims else "anonymous",
            "oid": claims.get("oid", ""),
        }

    app.include_router(requirements_router, dependencies=[Depends(require_user)])

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)
