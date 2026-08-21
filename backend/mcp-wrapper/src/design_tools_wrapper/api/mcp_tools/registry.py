"""The design-tools MCP server: exposes tools-service's deterministic
capabilities (diagram rendering, design validation, work breakdown CSV
export) as MCP tools.

Mirrors Parnell-AI-Persona-Agent's per-capability wrapper shape (see
``backend/mcp-wrapper/src/architecture_design_wrapper/api/mcp_tools
/registry.py`` there) - a ``FastMCP`` instance with one ``@mcp.tool()``
per capability, each just calling through to
``src.design_tools_wrapper.application.tool_calls``. This is the only
thing the orchestrator's ``app/infrastructure/tools_client.py`` talks to;
it never reaches tools-service directly.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from src.design_tools_wrapper.application.tool_calls import (
    export_technical_design,
    export_work_breakdown,
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
async def generate_architecture_diagram_tool(
    design_json: str,
    version: int = 1,
    generated_at: str = "TBD",
) -> str:
    """Render a SystemDesignArtifact (JSON) as the two required
    architecture-generation-phase diagrams: the Logical Architecture
    Diagram and the Azure Service Mapping Diagram.

    Args:
        design_json: JSON-serialized SystemDesignArtifact.
        version: the design version being rendered - stamped into each
            diagram's metadata block, never invented.
        generated_at: ISO timestamp of when this render was requested -
            stamped into each diagram's metadata block as "Last updated".

    Returns:
        JSON envelope: ``{"ok": bool, "status_code": int, "body": {...}}``.
        ``body`` is ``{"logical_svg": "<svg>...</svg>",
        "azure_mapping_svg": "<svg>...</svg>"}`` when ``ok`` is true, or
        ``{"detail": "..."}`` when rendering failed.
    """

    return await generate_architecture_diagram(design_json, version, generated_at)


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


@mcp.tool()
async def export_work_breakdown_tool(
    breakdown_json: str,
    requirements_json: str,
    design_json: str,
) -> str:
    """Validate a WorkBreakdownArtifact's (JSON) traceability and render
    it to an import-ready CSV.

    Args:
        breakdown_json: JSON-serialized WorkBreakdownArtifact.
        requirements_json: JSON-serialized RequirementsArtifact the
            breakdown was generated from.
        design_json: JSON-serialized SystemDesignArtifact the breakdown
            was generated from.

    Returns:
        JSON envelope: ``{"ok": bool, "status_code": int, "body": {...}}``.
        ``body`` is the ``WorkBreakdownExport`` (CSV text plus validation
        summary) when ``ok`` is true, or ``{"detail": "..."}`` when
        export failed.
    """

    return await export_work_breakdown(breakdown_json, requirements_json, design_json)


@mcp.tool()
async def export_technical_design_tool(
    document_json: str,
    design_json: str,
    requirements_json: str,
    work_breakdown_json: str,
) -> str:
    """Render a TechnicalDesignArtifact (JSON) to a downloadable ``.docx``
    file, with the approved architecture diagram embedded.

    Args:
        document_json: JSON-serialized TechnicalDesignArtifact.
        design_json: JSON-serialized SystemDesignArtifact whose
            architecture diagram is embedded in the rendered document.
        requirements_json: JSON-serialized RequirementsArtifact referenced
            by the document's traceability appendix.
        work_breakdown_json: JSON-serialized WorkBreakdownArtifact
            referenced by the document's traceability appendix.

    Returns:
        JSON envelope: ``{"ok": bool, "status_code": int, "body": {...}}``.
        ``body`` is the ``TechnicalDesignExport`` (base64 ``.docx`` bytes
        plus rendering summary) when ``ok`` is true, or
        ``{"detail": "..."}`` when export failed.
    """

    return await export_technical_design(
        document_json, design_json, requirements_json, work_breakdown_json
    )
