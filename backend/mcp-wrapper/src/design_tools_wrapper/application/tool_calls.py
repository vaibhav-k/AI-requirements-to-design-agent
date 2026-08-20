"""Translate MCP tool calls into plain REST calls against tools-service.

This module is intentionally "dumb": no domain typing, no business logic
— it deserializes the JSON string an MCP tool received, POSTs it to
tools-service, and serializes the response back to a JSON string. All the
actual behavior (rendering, validation) lives in tools-service; this is
just the wire adapter, the same "pure protocol adapter, no business
logic" role Parnell-AI-Persona-Agent's per-capability wrappers play (see
``backend/mcp-wrapper/src/architecture_design_wrapper/application
/tool_calls.py`` there).

Working with raw JSON strings rather than declaring Pydantic request/
response models here (unlike Parnell's wrappers) matches this project's
own existing MCP surface's convention — ``app/mcp/server.py``'s tools all
take/return ``*_json: str`` for the same artifact types already, so this
internal wrapper does the same rather than introducing a second style.

A tools-service rejection (422 — an invalid diagram spec, a failed
validation) is an ordinary, expected outcome here, not a transport
failure: both tool functions always return normally, wrapping the result
in an envelope — ``{"ok": bool, "status_code": int, "body": {...}}`` —
rather than raising and relying on the MCP protocol's own
``CallToolResult.isError``/exception-text plumbing to carry structured
error detail back to the caller. The orchestrator's MCP client
(``app/infrastructure/tools_client.py``) reads ``ok``/``body`` directly
and raises the right typed error itself (``ArchitectureValidationError``
vs. ``DiagramGenerationError``) — simpler than parsing an error string
back out of MCP's own error-content format.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from src.design_tools_wrapper.infrastructure.config import get_settings

logger = logging.getLogger(__name__)


async def _post(path: str, design_json: str) -> dict[str, Any]:
    """POST ``design_json`` to tools-service and return the envelope
    described in this module's docstring. Never raises for a tools-service
    4xx/5xx — only for something lower-level (DNS, connection refused,
    timeout), which callers let propagate as an ordinary exception since
    there's no sensible envelope to build without a response at all.
    """

    settings = get_settings()
    url = f"{settings.tools_service_base_url.rstrip('/')}{path}"
    payload = json.loads(design_json)

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


async def generate_architecture_diagram(design_json: str) -> str:
    """Call tools-service's diagram-rendering endpoint.

    Returns a JSON envelope; ``body`` is ``{"svg": "..."}`` when
    ``ok`` is true, or ``{"detail": "..."}`` when it's false.
    """

    envelope = await _post("/tools/diagrams/generate", design_json)
    return json.dumps(envelope)


async def validate_system_design(design_json: str) -> str:
    """Call tools-service's design-validation endpoint.

    Returns a JSON envelope; ``body`` is ``{"valid": true, "design": {...}}``
    when ``ok`` is true, or ``{"detail": "..."}`` when it's false.
    """

    envelope = await _post("/tools/designs/validate", design_json)
    return json.dumps(envelope)
