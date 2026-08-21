"""Unit tests for the design-tools wrapper's httpx translation layer.

Mocks ``httpx.AsyncClient`` rather than running a real tools-service
process - this wrapper's only job is "deserialize, POST, wrap the
response in an envelope, reserialize", so that's what's under test, not
tools-service's own behavior (covered by ``backend/tools-service/tests``).
"""

from __future__ import annotations

import json

import httpx
import pytest

from src.design_tools_wrapper.application.tool_calls import (
    export_technical_design,
    export_work_breakdown,
    generate_architecture_diagram,
    validate_system_design,
)

_DESIGN_JSON = json.dumps({"architecture_summary": "A design.", "components": []})
_REQUIREMENTS_JSON = json.dumps(
    {
        "summary": "s",
        "business_goal": "g",
        "actors": [],
        "functional_requirements": [],
        "non_functional_requirements": [],
        "data_requirements": [],
        "integration_requirements": [],
        "constraints": [],
        "assumptions": [],
        "open_questions": [],
    }
)
_BREAKDOWN_JSON = json.dumps({"features": [], "ambiguities": []})
_DOCUMENT_JSON = json.dumps(
    {
        "document_title": "Technical Design",
        "sections": [{"title": "Overview", "level": 1, "body": "Overview text."}],
    }
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.is_error = status_code >= 400
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.posted_to: str | None = None

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def post(self, url: str, json: dict) -> _FakeResponse:  # noqa: A002
        self.posted_to = url
        return self._response


@pytest.mark.asyncio
async def test_generate_architecture_diagram_envelope_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeAsyncClient(_FakeResponse(200, {"svg": "<svg></svg>"}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: fake_client)

    result = json.loads(await generate_architecture_diagram(_DESIGN_JSON))

    assert result == {
        "ok": True,
        "status_code": 200,
        "body": {"svg": "<svg></svg>"},
    }
    assert fake_client.posted_to is not None
    assert fake_client.posted_to.endswith("/tools/diagrams/generate")


@pytest.mark.asyncio
async def test_validate_system_design_envelope_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeAsyncClient(
        _FakeResponse(422, {"detail": "Component IDs must be unique."})
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: fake_client)

    result = json.loads(await validate_system_design(_DESIGN_JSON))

    assert result["ok"] is False
    assert result["status_code"] == 422
    assert "unique" in result["body"]["detail"]


@pytest.mark.asyncio
async def test_export_work_breakdown_envelope_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeAsyncClient(
        _FakeResponse(200, {"csv_text": "feature,story,task\r\n"})
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: fake_client)

    result = json.loads(
        await export_work_breakdown(_BREAKDOWN_JSON, _REQUIREMENTS_JSON, _DESIGN_JSON)
    )

    assert result == {
        "ok": True,
        "status_code": 200,
        "body": {"csv_text": "feature,story,task\r\n"},
    }
    assert fake_client.posted_to is not None
    assert fake_client.posted_to.endswith("/tools/work-breakdown/export")


@pytest.mark.asyncio
async def test_export_work_breakdown_envelope_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeAsyncClient(
        _FakeResponse(422, {"detail": "Task has no traceability."})
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: fake_client)

    result = json.loads(
        await export_work_breakdown(_BREAKDOWN_JSON, _REQUIREMENTS_JSON, _DESIGN_JSON)
    )

    assert result["ok"] is False
    assert result["status_code"] == 422
    assert "traceability" in result["body"]["detail"]


@pytest.mark.asyncio
async def test_export_technical_design_envelope_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeAsyncClient(
        _FakeResponse(
            200, {"docx_base64": "ZmFrZQ==", "filename": "technical-design.docx"}
        )
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: fake_client)

    result = json.loads(
        await export_technical_design(
            _DOCUMENT_JSON, _DESIGN_JSON, _REQUIREMENTS_JSON, _BREAKDOWN_JSON
        )
    )

    assert result == {
        "ok": True,
        "status_code": 200,
        "body": {"docx_base64": "ZmFrZQ==", "filename": "technical-design.docx"},
    }
    assert fake_client.posted_to is not None
    assert fake_client.posted_to.endswith("/tools/technical-design/export")


@pytest.mark.asyncio
async def test_export_technical_design_envelope_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeAsyncClient(
        _FakeResponse(422, {"detail": "The technical design document has no sections."})
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: fake_client)

    result = json.loads(
        await export_technical_design(
            _DOCUMENT_JSON, _DESIGN_JSON, _REQUIREMENTS_JSON, _BREAKDOWN_JSON
        )
    )

    assert result["ok"] is False
    assert result["status_code"] == 422
    assert "sections" in result["body"]["detail"]
