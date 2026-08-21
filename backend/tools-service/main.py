"""tools-service entry point.

Run with:

    uvicorn main:app --reload --port 8100

or, in production, the way the Dockerfile does it (see that file).

This service is deliberately deterministic-only - no Azure OpenAI client
exists anywhere in it, and none of its dependencies (``fastapi``,
``graphviz``, ``pydantic``) can reach the network on their own. It is
reached only by ``backend/mcp-wrapper``, never directly by the frontend or
by end users - see the root README's architecture section for the full
request path (orchestrator -> mcp-wrapper -> tools-service).
"""

from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI

from src.api.routes.diagrams import router as diagrams_router
from src.api.routes.documents import router as documents_router
from src.api.routes.validation import router as validation_router
from src.api.routes.work_breakdown import router as work_breakdown_router
from src.infrastructure.config import get_settings

logging.basicConfig(level=logging.INFO)


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Requirements -> Design Agent: Tools Service", version="0.1.0"
    )

    app.include_router(diagrams_router)
    app.include_router(validation_router)
    app.include_router(work_breakdown_router)
    app.include_router(documents_router)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)
