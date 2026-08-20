"""mcp-wrapper entry point.

Mirrors Parnell-AI-Persona-Agent's ``backend/mcp-wrapper/combined_main.py``:
a single Starlette app mounting every wrapper's ``streamable_http_app()``
routes, so one process/port serves all wrapper MCP endpoints (today, just
``design-tools`` — see the root README for why this project's tools
surface is small enough not to need Parnell's five-wrappers split).

Run with:

    python combined_main.py

or, in production, the way the Dockerfile does it (see that file).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from collections.abc import AsyncIterator

import uvicorn
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.applications import Starlette

from src.design_tools_wrapper.api.mcp_tools.registry import mcp as design_tools_mcp

logger = logging.getLogger(__name__)

WRAPPERS = [design_tools_mcp]


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WRAPPERS_GATEWAY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8200
    log_level: str = "INFO"


def build_app() -> Starlette:
    """Build the Starlette app that serves all the wrapper MCP endpoints."""

    routes = []
    for wrapper in WRAPPERS:
        app = wrapper.streamable_http_app()
        routes.extend(app.routes)

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with contextlib.AsyncExitStack() as stack:
            for wrapper in WRAPPERS:
                await stack.enter_async_context(wrapper.session_manager.run())
            logger.info(
                "Gateway ready - %d wrapper(s): %s",
                len(WRAPPERS),
                ", ".join(
                    f"{w.name} @ {w.settings.streamable_http_path}" for w in WRAPPERS
                ),
            )
            yield

    return Starlette(routes=routes, lifespan=lifespan)


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    if sys.platform == "win32":
        # McpToolsClient (backend/orchestrator/app/infrastructure
        # /tools_client.py) opens a fresh MCP session per call rather than
        # holding one open — matching this wrapper's own
        # stateless_http=True design — so short-lived connections open and
        # close constantly here. Windows' default ProactorEventLoop logs a
        # spurious "ConnectionResetError [WinError 10054]" from
        # _ProactorBasePipeTransport._call_connection_lost on every one of
        # those closes; it's purely a Windows/asyncio logging quirk (the
        # request itself still completes and returns 200 OK) and doesn't
        # occur on Linux/macOS, so it's only worth switching event loop
        # policy here, not fixing anything upstream. The selector loop
        # doesn't have this quirk and is otherwise equivalent for this
        # single-process HTTP server's needs.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    settings = GatewaySettings()
    uvicorn.run(
        build_app(),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
