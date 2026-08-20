"""The design-tools MCP server: exposes tools-service's two deterministic
capabilities (diagram rendering, design validation) as MCP tools.

Mirrors Parnell-AI-Persona-Agent's per-capability wrapper shape (see
``backend/mcp-wrapper/src/architecture_design_wrapper/api/mcp_tools
/registry.py`` there) — a ``FastMCP`` instance with one ``@mcp.tool()``
per capability, each just calling through to
``src.design_tools_wrapper.application.tool_calls``. This is the only
thing the orchestrator's ``app/infrastructure/tools_client.py`` talks to;
it never reaches tools-service directly.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from src.design_tools_wrapper.application.tool_calls import (
    generate_architecture_diagram,
    validate_system_design,
)
from src.design_tools_wrapper.infrastructure.config import get_settings

settings = get_settings()

mcp = FastMCP(
    name="design-tools",
    host=settings.host,
    port=settings.port,
    stateless_http=True,
    streamable_http_path=settings.path,
)


@mcp.tool()
async def generate_architecture_diagram_tool(design_json: str) -> str:
    """Render a SystemDesignArtifact (JSON) as an SVG architecture diagram.

    Args:
        design_json: JSON-serialized SystemDesignArtifact.

    Returns:
        JSON envelope: ``{"ok": bool, "status_code": int, "body": {...}}``.
        ``body`` is ``{"svg": "<svg>...</svg>"}`` when ``ok`` is true, or
        ``{"detail": "..."}`` when rendering failed.
    """

    return await generate_architecture_diagram(design_json)


@mcp.tool()
async def validate_system_design_tool(design_json: str) -> str:
    """Validate a SystemDesignArtifact's (JSON) semantic integrity.

    Args:
        design_json: JSON-serialized SystemDesignArtifact.

    Returns:
        JSON envelope: ``{"ok": bool, "status_code": int, "body": {...}}``.
        ``body`` is ``{"valid": true, "design": {...}}`` when ``ok`` is
        true, or ``{"detail": "..."}`` when validation failed.
    """

    return await validate_system_design(design_json)
