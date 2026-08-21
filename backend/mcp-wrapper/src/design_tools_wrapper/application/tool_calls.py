"""Translate MCP tool calls into plain REST calls against tools-service.

This module is intentionally "dumb": no domain typing, no business logic
- it deserializes the JSON string an MCP tool received, POSTs it to
tools-service, and serializes the response back to a JSON string. All the
actual behavior (rendering, validation) lives in tools-service; this is
just the wire adapter, the same "pure protocol adapter, no business
logic" role Parnell-AI-Persona-Agent's per-capability wrappers play (see
``backend/mcp-wrapper/src/architecture_design_wrapper/application
/tool_calls.py`` there).

Working with raw JSON strings rather than declaring Pydantic request/
response models here (unlike Parnell's wrappers) matches this project's
own existing MCP surface's convention - ``app/mcp/server.py``'s tools all
take/return ``*_json: str`` for the same artifact types already, so this
internal wrapper does the same rather than introducing a second style.

A tools-service rejection (422 - an invalid diagram spec, a failed
validation) is an ordinary, expected outcome here, not a transport
failure: both tool functions always return normally, wrapping the result
in an envelope - ``{"ok": bool, "status_code": int, "body": {...}}`` -
rather than raising and relying on the MCP protocol's own
``CallToolResult.isError``/exception-text plumbing to carry structured
error detail back to the caller. The orchestrator's MCP client
(``app/infrastructure/tools_client.py``) reads ``ok``/``body`` directly
and raises the right typed error itself (``ArchitectureValidationError``
vs. ``DiagramGenerationError``) - simpler than parsing an error string
back out of MCP's own error-content format.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from src.design_tools_wrapper.infrastructure.config import get_settings

logger = logging.getLogger(__name__)


async def _post_payload(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST ``payload`` to tools-service and return the envelope described
    in this module's docstring. Never raises for a tools-service 4xx/5xx -
    only for something lower-level (DNS, connection refused, timeout),
    which callers let propagate as an ordinary exception since there's no
    sensible envelope to build without a response at all.
    """

    settings = get_settings()
    url = f"{settings.tools_service_base_url.rstrip('/')}{path}"

    async with httpx.AsyncClient(timeout=settings.tools_service_timeout) as client:
        response = await client.post(url, json=payload)

    try:
        body = response.json()
    except ValueError:
        body = {"detail": response.text}

    return {
        "ok": not response.is_error,
        "status_code": response.status_code,
        "body": body,
    }


async def _post(path: str, design_json: str) -> dict[str, Any]:
    """``_post_payload`` for the common case: the whole request body is
    one already-JSON-encoded artifact string."""

    return await _post_payload(path, json.loads(design_json))


async def generate_architecture_diagram(
    design_json: str,
    version: int = 1,
    generated_at: str = "TBD",
) -> str:
    """Call tools-service's diagram-rendering endpoint.

    ``version``/``generated_at`` feed the deterministic diagram-metadata
    block tools-service renders on each diagram (see
    ``src/api/routes/diagrams.py``) - never invented by the LLM.

    Returns a JSON envelope; ``body`` is ``{"logical_svg": "...",
    "azure_mapping_svg": "..."}`` when ``ok`` is true, or
    ``{"detail": "..."}`` when it's false.
    """

    payload = {
        "design": json.loads(design_json),
        "version": version,
        "generated_at": generated_at,
    }
    envelope = await _post_payload("/tools/diagrams/generate", payload)
    return json.dumps(envelope)


async def validate_system_design(design_json: str) -> str:
    """Call tools-service's design-validation endpoint.

    Returns a JSON envelope; ``body`` is ``{"valid": true, "design": {...}}``
    when ``ok`` is true, or ``{"detail": "..."}`` when it's false.
    """

    envelope = await _post("/tools/designs/validate", design_json)
    return json.dumps(envelope)


async def export_work_breakdown(
    breakdown_json: str,
    requirements_json: str,
    design_json: str,
) -> str:
    """Call tools-service's work-breakdown export endpoint.

    Unlike ``generate_architecture_diagram``/``validate_system_design``,
    this tool's request body is three separate artifacts rather than one -
    still assembled here without any domain typing or business logic, the
    same "dumb wire adapter" role this module's docstring describes; the
    only thing this function does that ``_post`` doesn't is combine three
    already-JSON-encoded strings into the one payload dict tools-service's
    ``WorkBreakdownExportRequest`` expects.

    Returns a JSON envelope; ``body`` is the ``WorkBreakdownExport`` (CSV
    text plus validation summary) when ``ok`` is true, or
    ``{"detail": "..."}`` when it's false.
    """

    payload = {
        "breakdown": json.loads(breakdown_json),
        "requirements": json.loads(requirements_json),
        "design": json.loads(design_json),
    }

    envelope = await _post_payload("/tools/work-breakdown/export", payload)
    return json.dumps(envelope)


async def export_technical_design(
    document_json: str,
    design_json: str,
    requirements_json: str,
    work_breakdown_json: str,
) -> str:
    """Call tools-service's technical-design export endpoint.

    Same "assemble four already-JSON-encoded strings into one payload
    dict" shape as ``export_work_breakdown`` above - the technical-design
    analogue, one artifact wider since the rendered document's
    traceability appendix and embedded architecture diagram both need
    their own source artifact.

    Returns a JSON envelope; ``body`` is the ``TechnicalDesignExport``
    (base64 ``.docx`` bytes plus rendering summary) when ``ok`` is true,
    or ``{"detail": "..."}`` when it's false.
    """

    payload = {
        "document": json.loads(document_json),
        "design": json.loads(design_json),
        "requirements": json.loads(requirements_json),
        "work_breakdown": json.loads(work_breakdown_json),
    }

    envelope = await _post_payload("/tools/technical-design/export", payload)
    return json.dumps(envelope)
