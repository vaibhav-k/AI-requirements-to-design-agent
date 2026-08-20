"""Reaches the design-tools MCP gateway (``backend/mcp-wrapper``) for the
two deterministic capabilities that used to run in-process here:
architecture diagram rendering and design validation.

Before the tools-service split (see README -> "Service Architecture"),
``DiagramRendererPort`` and ``ArchitectureValidatorPort`` were both
implemented by plain, synchronous, in-process classes
(``app.design.diagram.ArchitectureDiagramGenerator`` and
``app.design.validator.ArchitectureValidator``). Neither class exists in
this codebase any more — both moved wholesale to ``backend/tools-service``,
since they're pure, LLM-free logic and the orchestrator/tools-service
split's whole point is keeping every LLM call (and only LLM calls) in the
orchestrator. ``McpToolsClient`` is the adapter that now implements both
ports by reaching that logic over the network instead:

    McpToolsClient (this class, sync ports)
        -> mcp.client.streamable_http + mcp.ClientSession (async MCP call)
        -> backend/mcp-wrapper's "design-tools" FastMCP server
        -> plain httpx REST call
        -> backend/tools-service

This mirrors Parnell-AI-Persona-Agent's own orchestrator-side MCP client
(``backend/orchestrator/src/infrastructure/mcp_client.py``) — same
``streamable_http_client`` + ``ClientSession`` shape, same
"initialize, call_tool, done" lifecycle per call (no session reuse across
calls, matching the wrapper's ``stateless_http=True`` server).

Two differences from Parnell's client, both driven by the mcp-wrapper
side's own design (see ``backend/mcp-wrapper/src/design_tools_wrapper
/application/tool_calls.py``):

- Both ports here are *synchronous* (``DiagramRendererPort.generate`` and
  ``ArchitectureValidatorPort.validate`` are plain sync methods, matching
  every other call site's expectations — the CLI, the sync FastAPI
  routes, and ``app/mcp/server.py``'s own tool functions never awaited
  the old in-process classes either). ``app.infrastructure.sync_bridge
  .run_sync`` bridges each call's async MCP round trip when the calling
  thread has no event loop of its own already running. Unlike every
  other ``run_sync`` caller, though, this client can also legitimately be
  reached from *inside* an already-running loop: the image-upload routes
  (``app/api/routes/requirements.py``'s ``start_run_from_upload``/
  ``refine_run_from_upload``) are ``async def`` — they need to ``await``
  classification/interpretation — and their sync helper
  ``_apply_diagram_to_record`` calls straight into
  ``ArchitectureSession.generate_from_design``, landing back on that same
  running loop. ``run_sync`` deliberately raises in that situation for
  its *other* callers (there, it usually means an async function forgot
  to ``await`` something), so this client can't reuse it unconditionally
  — see ``_run_coro`` below for the fallback.
- The mcp-wrapper's tools never raise on a tools-service-level failure —
  they always return an ``{"ok", "status_code", "body"}`` envelope (see
  that module's docstring for the rationale). This client is what
  inspects the envelope and raises the typed application error
  (``DiagramGenerationError`` / ``ArchitectureValidationError``) that the
  rest of the codebase already expects from these ports.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.application.errors import ArchitectureValidationError, DiagramGenerationError
from app.domain.design import SystemDesignArtifact
from app.infrastructure.sync_bridge import run_sync

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _run_coro(coro: Coroutine[object, object, T]) -> T:
    """Run ``coro`` to completion, whether or not the calling thread
    already has a running event loop.

    ``DiagramRendererPort``/``ArchitectureValidatorPort`` are documented
    as plain synchronous methods, safe to call from anywhere — see this
    module's docstring for why that includes, unlike every other
    ``run_sync`` caller, being invoked from inside an already-running
    loop. When there's no running loop, this is exactly ``run_sync``.
    When there is one, the coroutine runs to completion on a dedicated
    worker thread with its own fresh event loop instead — that thread
    never touches the caller's loop or any object created on it, so
    there's no cross-loop sharing to worry about, just a second loop
    running the MCP round trip in parallel while the caller's own loop
    stays free for whatever else is going on.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return run_sync(coro, caller="McpToolsClient")

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


_GENERATE_DIAGRAM_TOOL = "generate_architecture_diagram_tool"
_VALIDATE_DESIGN_TOOL = "validate_system_design_tool"


def _extract_envelope(result: Any) -> dict[str, Any]:
    """Pull the ``{"ok", "status_code", "body"}`` envelope out of an MCP
    ``CallToolResult``.

    The design-tools wrapper's tools are declared ``-> str`` and return a
    JSON-encoded string (the envelope, serialized). FastMCP (as of the
    ``mcp[cli]`` version this project pins — see this repo's
    ``requirements.txt``) still populates ``structuredContent`` even for a
    plain ``-> str`` return, but as ``{"result": "<the raw JSON string>"}``
    rather than the already-parsed envelope dict — confirmed empirically
    against a live mcp-wrapper instance, since the alternative
    ("structuredContent already holds the parsed dict") looked equally
    plausible from the SDK's docs alone and would have been silently wrong
    here. So both branches below end in the same ``json.loads`` on a
    string; the only difference is where that string comes from.
    """

    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict) and isinstance(structured.get("result"), str):
        parsed: dict[str, Any] = json.loads(structured["result"])
        return parsed

    content = getattr(result, "content", None) or []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            return parsed

    raise RuntimeError("design-tools MCP tool returned no parseable content.")


class McpToolsClient:
    """Implements ``DiagramRendererPort`` and ``ArchitectureValidatorPort``
    by calling the design-tools MCP gateway.

    Constructed once by ``app.infrastructure.composition
    .build_design_tools_client`` and shared across call sites the same way
    the agent-backed use cases are — see that function's docstring for how
    the gateway URL is configured.
    """

    def __init__(self, mcp_url: str) -> None:
        self._mcp_url = mcp_url

    async def _call_tool(
        self, tool_name: str, design: SystemDesignArtifact
    ) -> dict[str, Any]:
        payload = {"design_json": design.model_dump_json()}

        async with streamable_http_client(self._mcp_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, payload)

        if getattr(result, "isError", False):
            raise RuntimeError(
                f"design-tools MCP tool {tool_name!r} reported a "
                f"transport-level error: {result}"
            )

        return _extract_envelope(result)

    # -- DiagramRendererPort -------------------------------------------------

    def generate(self, design: SystemDesignArtifact) -> str:
        """Render ``design`` as an SVG diagram via the design-tools gateway.

        Raises ``DiagramGenerationError`` if tools-service reports a
        rendering failure (or if the gateway/tools-service can't be
        reached at all).
        """

        try:
            envelope = _run_coro(self._call_tool(_GENERATE_DIAGRAM_TOOL, design))
        except Exception as exc:  # noqa: BLE001 - re-raised as the port's own error type
            raise DiagramGenerationError(
                f"Failed to reach the design-tools service for diagram rendering: {exc}"
            ) from exc

        if not envelope.get("ok", False):
            detail = envelope.get("body", {}).get(
                "detail", "Unknown diagram rendering failure."
            )
            raise DiagramGenerationError(detail)

        svg = envelope.get("body", {}).get("svg")
        if not svg:
            raise DiagramGenerationError(
                "design-tools service reported success but returned no SVG content."
            )

        return str(svg)

    # -- ArchitectureValidatorPort --------------------------------------------

    def validate(self, design: SystemDesignArtifact) -> SystemDesignArtifact:
        """Validate ``design`` via the design-tools gateway.

        Raises ``ArchitectureValidationError`` if tools-service reports a
        validation failure. Reachability failures are also surfaced as
        ``ArchitectureValidationError`` (rather than a generic
        ``RuntimeError``) since every existing caller of this port already
        only catches that one exception type.
        """

        try:
            envelope = _run_coro(self._call_tool(_VALIDATE_DESIGN_TOOL, design))
        except Exception as exc:  # noqa: BLE001 - re-raised as the port's own error type
            raise ArchitectureValidationError(
                f"Failed to reach the design-tools service for validation: {exc}"
            ) from exc

        if not envelope.get("ok", False):
            detail = envelope.get("body", {}).get(
                "detail", "Unknown validation failure."
            )
            raise ArchitectureValidationError(detail)

        validated = envelope.get("body", {}).get("design")
        if validated is None:
            raise ArchitectureValidationError(
                "design-tools service reported success but returned no "
                "validated design."
            )

        return SystemDesignArtifact.model_validate(validated)
