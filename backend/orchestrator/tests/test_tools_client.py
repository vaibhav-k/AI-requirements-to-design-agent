"""Unit tests for ``app.infrastructure.tools_client.McpToolsClient``.

Mocks ``McpToolsClient._call_tool`` rather than a real MCP round trip -
this module's own job (translate an envelope into
``DiagramGenerationError``/``ArchitectureValidationError``, or a parsed
``SystemDesignArtifact``) is what's under test, not mcp-wrapper's or
tools-service's behavior (covered by their own test suites).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from app.application.errors import (
    ArchitectureValidationError,
    DiagramGenerationError,
    WorkBreakdownExportError,
)
from app.domain.design import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact
from app.domain.work_breakdown import WorkBreakdownArtifact, WorkBreakdownExport
from app.infrastructure.tools_client import McpToolsClient

_DESIGN = SystemDesignArtifact(architecture_summary="A design.")
_REQUIREMENTS = RequirementsArtifact(
    summary="s",
    business_goal="g",
    actors=[],
    functional_requirements=[],
    non_functional_requirements=[],
    data_requirements=[],
    integration_requirements=[],
    constraints=[],
    assumptions=[],
    open_questions=[],
)
_BREAKDOWN = WorkBreakdownArtifact()


def _client() -> McpToolsClient:
    return McpToolsClient(mcp_url="http://localhost:8200/mcp/design-tools")


def test_validate_returns_parsed_design_on_success() -> None:
    async def fake_call_tool(
        self: McpToolsClient, tool_name: str, design: SystemDesignArtifact
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "status_code": 200,
            "body": {"valid": True, "design": design.model_dump(mode="json")},
        }

    with patch.object(McpToolsClient, "_call_tool", fake_call_tool):
        result = _client().validate(_DESIGN)

    assert result == _DESIGN


def test_validate_raises_on_failure_envelope() -> None:
    async def fake_call_tool(
        self: McpToolsClient, tool_name: str, design: SystemDesignArtifact
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "status_code": 422,
            "body": {"detail": "Component IDs must be unique."},
        }

    with patch.object(McpToolsClient, "_call_tool", fake_call_tool):
        with pytest.raises(ArchitectureValidationError, match="unique"):
            _client().validate(_DESIGN)


def test_generate_returns_svg_on_success() -> None:
    async def fake_call_payload_tool(
        self: McpToolsClient, tool_name: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "status_code": 200,
            "body": {
                "logical_svg": "<svg>logical</svg>",
                "azure_mapping_svg": "<svg>azure</svg>",
            },
        }

    with patch.object(McpToolsClient, "_call_payload_tool", fake_call_payload_tool):
        diagrams = _client().generate(_DESIGN, 1, "2026-01-01T00:00:00+00:00")

    assert diagrams.logical_svg == "<svg>logical</svg>"
    assert diagrams.azure_mapping_svg == "<svg>azure</svg>"


def test_generate_raises_on_failure_envelope() -> None:
    async def fake_call_payload_tool(
        self: McpToolsClient, tool_name: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return {"ok": False, "status_code": 422, "body": {"detail": "bad design"}}

    with patch.object(McpToolsClient, "_call_payload_tool", fake_call_payload_tool):
        with pytest.raises(DiagramGenerationError, match="bad design"):
            _client().generate(_DESIGN, 1, "2026-01-01T00:00:00+00:00")


def test_validate_works_from_inside_a_running_event_loop() -> None:
    """Regression test: ``app/api/routes/requirements.py``'s
    ``start_run_from_upload``/``refine_run_from_upload`` are ``async def``
    (they need to ``await`` classification/interpretation), and their sync
    helper ``_apply_diagram_to_record`` calls straight into
    ``ArchitectureSession.generate_from_design`` -> this client, all still
    on that same running loop. ``sync_bridge.run_sync`` alone would raise
    "cannot be called from a running event loop" here - that's exactly
    the bug this test catches (see ``McpToolsClient``'s module docstring
    and ``_run_coro`` for the fix)."""

    async def fake_call_tool(
        self: McpToolsClient, tool_name: str, design: SystemDesignArtifact
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "status_code": 200,
            "body": {"valid": True, "design": design.model_dump(mode="json")},
        }

    async def route_handler() -> SystemDesignArtifact:
        # Mirrors the real call shape: an async route's call stack reaching
        # a *sync* call into the client, all on the same running loop.
        with patch.object(McpToolsClient, "_call_tool", fake_call_tool):
            return _client().validate(_DESIGN)

    result = asyncio.run(route_handler())

    assert result == _DESIGN


def test_generate_works_from_inside_a_running_event_loop() -> None:
    """Same regression as above, for the diagram-rendering port."""

    async def fake_call_payload_tool(
        self: McpToolsClient, tool_name: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "status_code": 200,
            "body": {
                "logical_svg": "<svg>logical</svg>",
                "azure_mapping_svg": "<svg>azure</svg>",
            },
        }

    async def route_handler() -> str:
        with patch.object(McpToolsClient, "_call_payload_tool", fake_call_payload_tool):
            return (
                _client().generate(_DESIGN, 1, "2026-01-01T00:00:00+00:00").logical_svg
            )

    assert asyncio.run(route_handler()) == "<svg>logical</svg>"


def test_export_returns_parsed_export_on_success() -> None:
    export = WorkBreakdownExport(csv_text="feature,story,task\r\n")

    async def fake_call_payload_tool(
        self: McpToolsClient, tool_name: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        assert set(payload) == {"breakdown_json", "requirements_json", "design_json"}
        return {
            "ok": True,
            "status_code": 200,
            "body": export.model_dump(mode="json"),
        }

    with patch.object(McpToolsClient, "_call_payload_tool", fake_call_payload_tool):
        result = _client().export(_BREAKDOWN, _REQUIREMENTS, _DESIGN)

    assert result == export


def test_export_raises_on_failure_envelope() -> None:
    async def fake_call_payload_tool(
        self: McpToolsClient, tool_name: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "status_code": 422,
            "body": {"detail": "Task has no traceability."},
        }

    with patch.object(McpToolsClient, "_call_payload_tool", fake_call_payload_tool):
        with pytest.raises(WorkBreakdownExportError, match="traceability"):
            _client().export(_BREAKDOWN, _REQUIREMENTS, _DESIGN)


def test_export_raises_when_unreachable() -> None:
    async def fake_call_payload_tool(
        self: McpToolsClient, tool_name: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        raise RuntimeError("connection refused")

    with patch.object(McpToolsClient, "_call_payload_tool", fake_call_payload_tool):
        with pytest.raises(WorkBreakdownExportError, match="connection refused"):
            _client().export(_BREAKDOWN, _REQUIREMENTS, _DESIGN)
