from __future__ import annotations

import base64
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_artifact_store,
    get_document_exporter,
    get_session_store,
    get_technical_design_writer,
)
from app.application.errors import (
    TechnicalDesignExportError,
    TechnicalDesignGenerationError,
)
from app.config import Settings
from app.domain.design import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact
from app.domain.session import SessionRecord
from app.domain.technical_design import (
    DesignSection,
    TechnicalDesignArtifact,
    TechnicalDesignExport,
)
from app.domain.work_breakdown import (
    WorkBreakdownArtifact,
    WorkBreakdownFeature,
    WorkBreakdownStory,
    WorkBreakdownTask,
)
from app.web.main import create_app


def make_requirements(**overrides: object) -> RequirementsArtifact:
    defaults: dict[str, object] = {
        "summary": "A todo app.",
        "business_goal": "Track tasks.",
        "actors": [],
        "functional_requirements": [],
        "non_functional_requirements": [],
        "data_requirements": [],
        "integration_requirements": [],
        "constraints": [],
        "assumptions": [],
        "open_questions": [],
    }
    defaults.update(overrides)
    return RequirementsArtifact.model_validate(defaults)


def make_design(**overrides: object) -> SystemDesignArtifact:
    defaults: dict[str, object] = {"architecture_summary": "A simple design."}
    defaults.update(overrides)
    return SystemDesignArtifact.model_validate(defaults)


def make_breakdown(**overrides: object) -> WorkBreakdownArtifact:
    defaults: dict[str, object] = {
        "features": [
            WorkBreakdownFeature(
                feature="Task management",
                stories=[
                    WorkBreakdownStory(
                        story="Create a task",
                        tasks=[
                            WorkBreakdownTask(
                                task="Add task API",
                                description="Expose an endpoint to create a task.",
                                effort="S",
                                requirement_ids=["FR-001"],
                                architecture_ids=["C-001"],
                            )
                        ],
                    )
                ],
            )
        ],
        "ambiguities": [],
    }
    defaults.update(overrides)
    return WorkBreakdownArtifact.model_validate(defaults)


def make_document(**overrides: object) -> TechnicalDesignArtifact:
    defaults: dict[str, object] = {
        "document_title": "Todo App Technical Design",
        "sections": [
            DesignSection(
                title="Architecture Overview",
                level=1,
                body="A simple design.",
                include_diagram=True,
            )
        ],
    }
    defaults.update(overrides)
    return TechnicalDesignArtifact.model_validate(defaults)


def make_export(**overrides: object) -> TechnicalDesignExport:
    defaults: dict[str, object] = {
        "docx_base64": base64.b64encode(b"fake docx bytes").decode("ascii"),
        "filename": "technical-design.docx",
    }
    defaults.update(overrides)
    return TechnicalDesignExport.model_validate(defaults)


@pytest.fixture
def fakes() -> dict[str, MagicMock]:
    technical_design_writer = MagicMock()
    technical_design_writer.execute = AsyncMock()

    return {
        "store": MagicMock(),
        "artifact_store": MagicMock(),
        "technical_design_writer": technical_design_writer,
        "document_exporter": MagicMock(),
    }


@pytest.fixture
def client(fakes: dict[str, MagicMock]) -> Iterator[TestClient]:
    """A ``TestClient`` with ``AUTH_ENABLED=false`` - see
    ``test_requirements_routes.py``'s identical fixture for why all three
    ``get_settings`` bindings need patching.
    """
    settings = Settings(auth_enabled=False)
    with patch("app.web.main.get_settings", return_value=settings):
        app = create_app()

    app.dependency_overrides[get_session_store] = lambda: fakes["store"]
    app.dependency_overrides[get_artifact_store] = lambda: fakes["artifact_store"]
    app.dependency_overrides[get_technical_design_writer] = lambda: fakes[
        "technical_design_writer"
    ]
    app.dependency_overrides[get_document_exporter] = lambda: fakes["document_exporter"]

    auth_patcher = patch("app.security.auth.get_settings", return_value=settings)
    ownership_patcher = patch("app.api.ownership.get_settings", return_value=settings)
    auth_patcher.start()
    ownership_patcher.start()
    try:
        yield TestClient(app)
    finally:
        auth_patcher.stop()
        ownership_patcher.stop()


def work_breakdown_record(**overrides: object) -> SessionRecord:
    defaults: dict[str, object] = {
        "session_id": "abc-123",
        "stage": "work_breakdown",
        "requirements_version": 1,
        "requirements": make_requirements(),
        "design_version": 1,
        "design": make_design(),
        "approval_status": "approved",
        "work_breakdown_version": 1,
        "work_breakdown": make_breakdown(),
    }
    defaults.update(overrides)
    return SessionRecord.model_validate(defaults)


# ---------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------


def test_generate_technical_design_rejects_when_not_in_work_breakdown_stage(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(session_id="abc-123", stage="architecture")
    fakes["store"].get.return_value = record

    response = client.post("/requirements-runs/abc-123/technical-design")

    assert response.status_code == 409
    fakes["technical_design_writer"].execute.assert_not_called()


def test_generate_technical_design_rejects_when_already_exists(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = work_breakdown_record(
        stage="technical_design",
        technical_design_version=1,
        technical_design=make_document(),
    )
    fakes["store"].get.return_value = record

    response = client.post("/requirements-runs/abc-123/technical-design")

    assert response.status_code == 409
    fakes["technical_design_writer"].execute.assert_not_called()


def test_generate_technical_design_generates_and_persists(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = work_breakdown_record()
    fakes["store"].get.return_value = record
    fakes["technical_design_writer"].execute.return_value = make_document()
    fakes[
        "artifact_store"
    ].save_technical_design_json.return_value = "dev/abc-123/technical-design/v1.json"

    stage_snapshots: list[str] = []

    def _snapshot_stage(r: SessionRecord) -> SessionRecord:
        stage_snapshots.append(r.stage)
        return r

    fakes["store"].upsert.side_effect = _snapshot_stage

    response = client.post("/requirements-runs/abc-123/technical-design")

    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "technical_design"
    assert body["technical_design_version"] == 1
    assert body["technical_design"]["document_title"] == "Todo App Technical Design"
    assert stage_snapshots == ["generating", "technical_design"]
    fakes["technical_design_writer"].execute.assert_called_once_with(
        record.requirements,
        record.design,
        record.work_breakdown,
        previous_document=None,
        refinement_input=None,
    )


def test_generate_technical_design_returns_422_and_reverts_stage_on_failure(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = work_breakdown_record()
    fakes["store"].get.return_value = record
    fakes[
        "technical_design_writer"
    ].execute.side_effect = TechnicalDesignGenerationError("boom")

    stage_snapshots: list[str] = []

    def _snapshot_stage(r: SessionRecord) -> SessionRecord:
        stage_snapshots.append(r.stage)
        return r

    fakes["store"].upsert.side_effect = _snapshot_stage

    response = client.post("/requirements-runs/abc-123/technical-design")

    assert response.status_code == 422
    assert stage_snapshots == ["generating", "work_breakdown"]
    assert record.error is not None
    assert record.technical_design_version == 0


# ---------------------------------------------------------------------
# Refine
# ---------------------------------------------------------------------


def test_refine_technical_design_rejects_when_no_document_yet(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = work_breakdown_record()
    fakes["store"].get.return_value = record

    response = client.post(
        "/requirements-runs/abc-123/technical-design/refine",
        json={"input": "Add a data retention section."},
    )

    assert response.status_code == 409
    fakes["technical_design_writer"].execute.assert_not_called()


def test_refine_technical_design_bumps_version_and_persists(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    previous = make_document()
    record = work_breakdown_record(
        stage="technical_design",
        technical_design_version=1,
        technical_design=previous,
    )
    fakes["store"].get.return_value = record
    refined = make_document(document_title="Todo App Technical Design v2")
    fakes["technical_design_writer"].execute.return_value = refined
    fakes[
        "artifact_store"
    ].save_technical_design_json.return_value = "dev/abc-123/technical-design/v2.json"

    response = client.post(
        "/requirements-runs/abc-123/technical-design/refine",
        json={"input": "Add a data retention section."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["technical_design_version"] == 2
    assert body["technical_design"]["document_title"] == (
        "Todo App Technical Design v2"
    )
    _, call_kwargs = fakes["technical_design_writer"].execute.call_args
    assert call_kwargs["previous_document"] == previous
    assert call_kwargs["refinement_input"] == "Add a data retention section."


def test_refine_technical_design_returns_422_and_reverts_stage_on_failure(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    previous = make_document()
    record = work_breakdown_record(
        stage="technical_design",
        technical_design_version=1,
        technical_design=previous,
    )
    fakes["store"].get.return_value = record
    fakes["technical_design_writer"].execute.side_effect = ValueError(
        "design must include at least one component."
    )

    stage_snapshots: list[str] = []

    def _snapshot_stage(r: SessionRecord) -> SessionRecord:
        stage_snapshots.append(r.stage)
        return r

    fakes["store"].upsert.side_effect = _snapshot_stage

    response = client.post(
        "/requirements-runs/abc-123/technical-design/refine", json={"input": "Add X."}
    )

    assert response.status_code == 422
    assert stage_snapshots == ["generating", "technical_design"]
    assert record.technical_design_version == 1
    assert record.technical_design == previous


# ---------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------


def test_get_technical_design_returns_404_when_none_generated(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = work_breakdown_record()
    fakes["store"].get.return_value = record

    response = client.get("/requirements-runs/abc-123/technical-design")

    assert response.status_code == 404


def test_get_technical_design_returns_the_current_document(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    document = make_document()
    record = work_breakdown_record(
        stage="technical_design",
        technical_design_version=1,
        technical_design=document,
    )
    fakes["store"].get.return_value = record

    response = client.get("/requirements-runs/abc-123/technical-design")

    assert response.status_code == 200
    assert response.json()["document_title"] == "Todo App Technical Design"


def test_list_technical_design_versions_returns_the_stores_list(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    fakes["store"].get.return_value = work_breakdown_record()
    fakes["artifact_store"].list_technical_design_versions.return_value = [1, 2]

    response = client.get("/requirements-runs/abc-123/technical-design/versions")

    assert response.status_code == 200
    assert response.json() == [1, 2]
    fakes["artifact_store"].list_technical_design_versions.assert_called_once_with(
        "abc-123"
    )


def test_get_technical_design_version_returns_the_stored_version(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    fakes["store"].get.return_value = work_breakdown_record()
    fakes[
        "artifact_store"
    ].get_technical_design_json.return_value = make_document().model_dump_json()

    response = client.get("/requirements-runs/abc-123/technical-design/1")

    assert response.status_code == 200
    assert response.json()["document_title"] == "Todo App Technical Design"
    fakes["artifact_store"].get_technical_design_json.assert_called_once_with(
        "abc-123", 1
    )


def test_get_technical_design_version_404s_when_not_stored(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    fakes["store"].get.return_value = work_breakdown_record()
    fakes["artifact_store"].get_technical_design_json.return_value = None

    response = client.get("/requirements-runs/abc-123/technical-design/99")

    assert response.status_code == 404


def test_get_technical_design_version_500s_on_malformed_content(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    fakes["store"].get.return_value = work_breakdown_record()
    fakes["artifact_store"].get_technical_design_json.return_value = "{not valid json"

    response = client.get("/requirements-runs/abc-123/technical-design/1")

    assert response.status_code == 500


# ---------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------


def test_export_technical_design_rejects_when_no_document_yet(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = work_breakdown_record()
    fakes["store"].get.return_value = record

    response = client.get("/requirements-runs/abc-123/technical-design/export")

    assert response.status_code == 409
    fakes["document_exporter"].export_document.assert_not_called()


def test_export_technical_design_returns_docx(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    document = make_document()
    record = work_breakdown_record(
        stage="technical_design",
        technical_design_version=1,
        technical_design=document,
    )
    fakes["store"].get.return_value = record
    docx_bytes = b"fake docx bytes"
    fakes["document_exporter"].export_document.return_value = make_export(
        docx_base64=base64.b64encode(docx_bytes).decode("ascii")
    )
    fakes[
        "artifact_store"
    ].save_technical_design_docx.return_value = "dev/abc-123/technical-design/v1.docx"

    response = client.get("/requirements-runs/abc-123/technical-design/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert response.content == docx_bytes
    fakes["artifact_store"].save_technical_design_docx.assert_called_once_with(
        session_id="abc-123", version=1, content=docx_bytes
    )
    # Stamped back onto the session record and persisted - see
    # `SessionRecord.technical_design_export_blob`'s docstring.
    assert record.technical_design_export_blob == (
        "dev/abc-123/technical-design/v1.docx"
    )
    fakes["store"].upsert.assert_called_once_with(record)


def test_export_technical_design_surfaces_export_errors_as_422(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = work_breakdown_record(
        stage="technical_design",
        technical_design_version=1,
        technical_design=make_document(),
    )
    fakes["store"].get.return_value = record
    fakes["document_exporter"].export_document.side_effect = TechnicalDesignExportError(
        "tools-service unreachable"
    )

    response = client.get("/requirements-runs/abc-123/technical-design/export")

    assert response.status_code == 422
    assert "tools-service unreachable" in response.json()["detail"]
    # The export failed before anything was persisted - no stamp, no upsert.
    fakes["store"].upsert.assert_not_called()
