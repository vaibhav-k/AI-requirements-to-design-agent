from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_artifact_store,
    get_session_store,
    get_work_breakdown_analyzer,
    get_work_breakdown_exporter,
)
from app.application.errors import (
    WorkBreakdownExportError,
    WorkBreakdownGenerationError,
)
from app.config import Settings
from app.domain.design import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact
from app.domain.session import SessionRecord
from app.domain.work_breakdown import (
    WorkBreakdownArtifact,
    WorkBreakdownExport,
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


def make_export(**overrides: object) -> WorkBreakdownExport:
    defaults: dict[str, object] = {"csv_text": "feature,story,task\n"}
    defaults.update(overrides)
    return WorkBreakdownExport.model_validate(defaults)


@pytest.fixture
def fakes() -> dict[str, MagicMock]:
    work_breakdown_analyzer = MagicMock()
    work_breakdown_analyzer.execute = AsyncMock()

    return {
        "store": MagicMock(),
        "artifact_store": MagicMock(),
        "work_breakdown_analyzer": work_breakdown_analyzer,
        "work_breakdown_exporter": MagicMock(),
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
    app.dependency_overrides[get_work_breakdown_analyzer] = lambda: fakes[
        "work_breakdown_analyzer"
    ]
    app.dependency_overrides[get_work_breakdown_exporter] = lambda: fakes[
        "work_breakdown_exporter"
    ]

    auth_patcher = patch("app.security.auth.get_settings", return_value=settings)
    ownership_patcher = patch("app.api.ownership.get_settings", return_value=settings)
    auth_patcher.start()
    ownership_patcher.start()
    try:
        yield TestClient(app)
    finally:
        auth_patcher.stop()
        ownership_patcher.stop()


def approved_architecture_record(**overrides: object) -> SessionRecord:
    defaults: dict[str, object] = {
        "session_id": "abc-123",
        "stage": "architecture",
        "requirements_version": 1,
        "requirements": make_requirements(),
        "design_version": 1,
        "design": make_design(),
        "approval_status": "approved",
    }
    defaults.update(overrides)
    return SessionRecord.model_validate(defaults)


# ---------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------


def test_generate_work_breakdown_rejects_when_not_in_architecture_stage(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(session_id="abc-123", stage="requirements")
    fakes["store"].get.return_value = record

    response = client.post("/requirements-runs/abc-123/work-breakdown")

    assert response.status_code == 409
    fakes["work_breakdown_analyzer"].execute.assert_not_called()


def test_generate_work_breakdown_rejects_when_architecture_not_approved(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = approved_architecture_record(approval_status="pending")
    fakes["store"].get.return_value = record

    response = client.post("/requirements-runs/abc-123/work-breakdown")

    assert response.status_code == 409
    fakes["work_breakdown_analyzer"].execute.assert_not_called()


def test_generate_work_breakdown_rejects_when_already_exists(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = approved_architecture_record(
        stage="work_breakdown",
        work_breakdown_version=1,
        work_breakdown=make_breakdown(),
    )
    fakes["store"].get.return_value = record

    response = client.post("/requirements-runs/abc-123/work-breakdown")

    assert response.status_code == 409
    fakes["work_breakdown_analyzer"].execute.assert_not_called()


def test_generate_work_breakdown_generates_and_persists(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = approved_architecture_record()
    fakes["store"].get.return_value = record
    fakes["work_breakdown_analyzer"].execute.return_value = make_breakdown()
    fakes[
        "artifact_store"
    ].save_work_breakdown_json.return_value = "dev/abc-123/work-breakdown/v1.json"

    stage_snapshots: list[str] = []

    def _snapshot_stage(r: SessionRecord) -> SessionRecord:
        stage_snapshots.append(r.stage)
        return r

    fakes["store"].upsert.side_effect = _snapshot_stage

    response = client.post("/requirements-runs/abc-123/work-breakdown")

    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "work_breakdown"
    assert body["work_breakdown_version"] == 1
    assert body["work_breakdown"]["features"][0]["feature"] == "Task management"
    assert stage_snapshots == ["generating", "work_breakdown"]
    fakes["work_breakdown_analyzer"].execute.assert_called_once_with(
        record.requirements,
        record.design,
        previous_breakdown=None,
        refinement_input=None,
    )


def test_generate_work_breakdown_returns_422_and_reverts_stage_on_failure(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = approved_architecture_record()
    fakes["store"].get.return_value = record
    fakes["work_breakdown_analyzer"].execute.side_effect = WorkBreakdownGenerationError(
        "boom"
    )

    stage_snapshots: list[str] = []

    def _snapshot_stage(r: SessionRecord) -> SessionRecord:
        stage_snapshots.append(r.stage)
        return r

    fakes["store"].upsert.side_effect = _snapshot_stage

    response = client.post("/requirements-runs/abc-123/work-breakdown")

    assert response.status_code == 422
    assert stage_snapshots == ["generating", "architecture"]
    assert record.error is not None
    assert record.work_breakdown_version == 0


# ---------------------------------------------------------------------
# Refine
# ---------------------------------------------------------------------


def test_refine_work_breakdown_rejects_when_no_breakdown_yet(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = approved_architecture_record()
    fakes["store"].get.return_value = record

    response = client.post(
        "/requirements-runs/abc-123/work-breakdown/refine",
        json={"input": "Add a delete-task task."},
    )

    assert response.status_code == 409
    fakes["work_breakdown_analyzer"].execute.assert_not_called()


def test_refine_work_breakdown_bumps_version_and_persists(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    previous = make_breakdown()
    record = approved_architecture_record(
        stage="work_breakdown",
        work_breakdown_version=1,
        work_breakdown=previous,
    )
    fakes["store"].get.return_value = record
    refined = make_breakdown(
        features=[
            WorkBreakdownFeature(feature="Task management", stories=[]),
            WorkBreakdownFeature(feature="Notifications", stories=[]),
        ]
    )
    fakes["work_breakdown_analyzer"].execute.return_value = refined
    fakes[
        "artifact_store"
    ].save_work_breakdown_json.return_value = "dev/abc-123/work-breakdown/v2.json"

    response = client.post(
        "/requirements-runs/abc-123/work-breakdown/refine",
        json={"input": "Add a notifications feature."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["work_breakdown_version"] == 2
    assert len(body["work_breakdown"]["features"]) == 2
    _, call_kwargs = fakes["work_breakdown_analyzer"].execute.call_args
    assert call_kwargs["previous_breakdown"] == previous
    assert call_kwargs["refinement_input"] == "Add a notifications feature."


def test_refine_work_breakdown_returns_422_and_reverts_stage_on_failure(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    previous = make_breakdown()
    record = approved_architecture_record(
        stage="work_breakdown",
        work_breakdown_version=1,
        work_breakdown=previous,
    )
    fakes["store"].get.return_value = record
    fakes["work_breakdown_analyzer"].execute.side_effect = ValueError(
        "design must include at least one component."
    )

    stage_snapshots: list[str] = []

    def _snapshot_stage(r: SessionRecord) -> SessionRecord:
        stage_snapshots.append(r.stage)
        return r

    fakes["store"].upsert.side_effect = _snapshot_stage

    response = client.post(
        "/requirements-runs/abc-123/work-breakdown/refine", json={"input": "Add X."}
    )

    assert response.status_code == 422
    assert stage_snapshots == ["generating", "work_breakdown"]
    assert record.work_breakdown_version == 1
    assert record.work_breakdown == previous


# ---------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------


def test_get_work_breakdown_returns_404_when_none_generated(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = approved_architecture_record()
    fakes["store"].get.return_value = record

    response = client.get("/requirements-runs/abc-123/work-breakdown")

    assert response.status_code == 404


def test_get_work_breakdown_returns_the_current_breakdown(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    breakdown = make_breakdown()
    record = approved_architecture_record(
        stage="work_breakdown", work_breakdown_version=1, work_breakdown=breakdown
    )
    fakes["store"].get.return_value = record

    response = client.get("/requirements-runs/abc-123/work-breakdown")

    assert response.status_code == 200
    assert response.json()["features"][0]["feature"] == "Task management"


def test_get_work_breakdown_404s_when_session_missing(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    fakes["store"].get.return_value = None

    response = client.get("/requirements-runs/abc-123/work-breakdown")

    assert response.status_code == 404


def test_list_work_breakdown_versions_returns_the_stores_list(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    fakes["store"].get.return_value = approved_architecture_record()
    fakes["artifact_store"].list_work_breakdown_versions.return_value = [1, 2]

    response = client.get("/requirements-runs/abc-123/work-breakdown/versions")

    assert response.status_code == 200
    assert response.json() == [1, 2]
    fakes["artifact_store"].list_work_breakdown_versions.assert_called_once_with(
        "abc-123"
    )


def test_get_work_breakdown_version_returns_the_stored_version(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    fakes["store"].get.return_value = approved_architecture_record()
    fakes[
        "artifact_store"
    ].get_work_breakdown_json.return_value = make_breakdown().model_dump_json()

    response = client.get("/requirements-runs/abc-123/work-breakdown/1")

    assert response.status_code == 200
    assert response.json()["features"][0]["feature"] == "Task management"
    fakes["artifact_store"].get_work_breakdown_json.assert_called_once_with(
        "abc-123", 1
    )


def test_get_work_breakdown_version_404s_when_not_stored(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    fakes["store"].get.return_value = approved_architecture_record()
    fakes["artifact_store"].get_work_breakdown_json.return_value = None

    response = client.get("/requirements-runs/abc-123/work-breakdown/99")

    assert response.status_code == 404


def test_get_work_breakdown_version_500s_on_malformed_content(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    fakes["store"].get.return_value = approved_architecture_record()
    fakes["artifact_store"].get_work_breakdown_json.return_value = "{not valid json"

    response = client.get("/requirements-runs/abc-123/work-breakdown/1")

    assert response.status_code == 500


# ---------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------


def test_export_work_breakdown_rejects_when_no_breakdown_yet(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = approved_architecture_record()
    fakes["store"].get.return_value = record

    response = client.get("/requirements-runs/abc-123/work-breakdown/export")

    assert response.status_code == 409
    fakes["work_breakdown_exporter"].export.assert_not_called()


def test_export_work_breakdown_returns_csv(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    breakdown = make_breakdown()
    record = approved_architecture_record(
        stage="work_breakdown", work_breakdown_version=1, work_breakdown=breakdown
    )
    fakes["store"].get.return_value = record
    fakes["work_breakdown_exporter"].export.return_value = make_export(
        csv_text="feature,story,task\nTask management,Create a task,Add task API\n"
    )
    fakes[
        "artifact_store"
    ].save_work_breakdown_csv.return_value = "dev/abc-123/work-breakdown/v1.csv"

    response = client.get("/requirements-runs/abc-123/work-breakdown/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "Add task API" in response.text
    fakes["artifact_store"].save_work_breakdown_csv.assert_called_once_with(
        session_id="abc-123", version=1, content=response.text
    )
    # Stamped back onto the session record and persisted - see
    # `SessionRecord.work_breakdown_export_blob`'s docstring for why this
    # pointer matters (letting a caller tell "already exported" without a
    # separate Blob round trip).
    assert record.work_breakdown_export_blob == "dev/abc-123/work-breakdown/v1.csv"
    fakes["store"].upsert.assert_called_once_with(record)


def test_export_work_breakdown_surfaces_export_errors_as_422(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = approved_architecture_record(
        stage="work_breakdown",
        work_breakdown_version=1,
        work_breakdown=make_breakdown(),
    )
    fakes["store"].get.return_value = record
    fakes["work_breakdown_exporter"].export.side_effect = WorkBreakdownExportError(
        "tools-service unreachable"
    )

    response = client.get("/requirements-runs/abc-123/work-breakdown/export")

    assert response.status_code == 422
    assert "tools-service unreachable" in response.json()["detail"]
    # The export failed before anything was persisted - no stamp, no upsert.
    fakes["store"].upsert.assert_not_called()
