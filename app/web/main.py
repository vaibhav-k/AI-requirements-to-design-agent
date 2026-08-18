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

from app.api.routes.artifacts import router as artifacts_router
from app.api.routes.requirements import router as requirements_router
from app.config import get_settings
from app.infrastructure.session_store import CosmosSessionStore
from app.security.auth import (
    ALL_APP_ROLES,
    current_claims,
    current_roles,
    principal_of,
    require_user,
)
from app.storage import AZURE_CONNECTION_STRING, AZURE_CONTAINER, ArtifactStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI) -> AsyncIterator[None]:
    """Construct the Cosmos session store and Blob artifact store once, at startup.

    Both are synchronous clients (see ``app/infrastructure/session_store.py``
    for why), so building them here — rather than lazily per-request — keeps
    the cost of the ``create_database_if_not_exists``/``create_container_if_not_exists``
    round-trip out of the request path.

    Named ``fastapi_app`` rather than ``app`` so it doesn't shadow this
    module's own top-level ``app = create_app()`` instance (the one
    ``uvicorn app.web.main:app`` actually serves) — same reasoning as
    ``create_app``'s local below.
    """
    session_store = CosmosSessionStore()
    session_store.start()
    fastapi_app.state.session_store = session_store

    artifact_store = ArtifactStore(
        connection_string=AZURE_CONNECTION_STRING,
        container_name=AZURE_CONTAINER,
    )
    fastapi_app.state.artifact_store = artifact_store

    try:
        yield
    finally:
        # Each store's close() is independent — one raising must not stop the
        # other from closing, and must not turn a normal shutdown (Ctrl+C,
        # SIGTERM, --reload restarting) into "Application shutdown failed."
        # the way an unguarded call did before (see the CosmosClient fix in
        # session_store.close()'s docstring). The broad `except Exception`
        # is intentional: these are third-party SDK `.close()` calls whose
        # exact failure modes aren't ours to enumerate, and any exception
        # here must be logged and swallowed, never allowed to mask the
        # other store's cleanup or turn a normal shutdown into a crash.
        for name, close in (
            ("session_store", session_store.close),
            ("artifact_store", artifact_store.close),
        ):
            try:
                close()
            except Exception:  # pylint: disable=broad-exception-caught
                logger.warning("Error closing %s during shutdown", name, exc_info=True)


def create_app() -> FastAPI:
    app_settings = get_settings()

    fastapi_app = FastAPI(
        title="AI Requirements → System Design Agent",
        version="0.2.0",
        lifespan=lifespan,
    )

    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @fastapi_app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        """Unauthenticated liveness probe."""
        return {"status": "ok"}

    @fastapi_app.get("/me", tags=["auth"], dependencies=[Depends(require_user)])
    async def whoami(request: Request) -> dict[str, object]:
        """Returns the caller's identity and App Roles.

        With ``AUTH_ENABLED=false`` this returns an empty/anonymous identity
        rather than 401ing, since ``require_user`` is a no-op in that mode —
        same behavior as every other route until real endpoints are added.
        ``roles`` in that mode is every role (``ALL_APP_ROLES``), not empty —
        it reports what the caller can actually *do*, and with auth
        disabled ``require_role`` lets every action through regardless of
        role, so reporting an empty list here would be misleading. The
        frontend uses this to grey out actions the signed-in user's role
        doesn't permit (see ``frontend/src/App.tsx``'s ``useCurrentUser``).
        """
        claims = current_claims(request)
        request_settings = get_settings()
        roles = (
            list(ALL_APP_ROLES)
            if not request_settings.auth_enabled
            else sorted(current_roles(request))
        )
        return {
            "authenticated": bool(claims),
            "principal": principal_of(claims) if claims else "anonymous",
            "oid": claims.get("oid", ""),
            "roles": roles,
        }

    fastapi_app.include_router(
        requirements_router, dependencies=[Depends(require_user)]
    )
    fastapi_app.include_router(artifacts_router, dependencies=[Depends(require_user)])

    return fastapi_app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)
