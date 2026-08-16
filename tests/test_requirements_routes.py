from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_artifact_store,
    get_design_analyzer,
    get_diagram_generator,
    get_requirements_analyzer,
    get_session_store,
    get_validator,
)
from app.config import Settings
from app.design.models import SystemDesignArtifact
from app.design.session import DesignGenerationWorkflowError
from app.infrastructure.session_store import SessionConflictError, SessionRecord
from app.models import RequirementsArtifact
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


@pytest.fixture
def fakes() -> dict[str, MagicMock]:
    return {
        "store": MagicMock(),
        "artifact_store": MagicMock(),
        "requirements_analyzer": MagicMock(),
        "design_analyzer": MagicMock(),
        "diagram_generator": MagicMock(),
        "validator": MagicMock(),
    }


@pytest.fixture
def client(fakes: dict[str, MagicMock]) -> TestClient:
    settings = Settings(auth_enabled=False)
    with patch("app.web.main.get_settings", return_value=settings):
        app = create_app()

    app.dependency_overrides[get_session_store] = lambda: fakes["store"]
    app.dependency_overrides[get_artifact_store] = lambda: fakes["artifact_store"]
    app.dependency_overrides[get_requirements_analyzer] = lambda: fakes[
        "requirements_analyzer"
    ]
    app.dependency_overrides[get_design_analyzer] = lambda: fakes["design_analyzer"]
    app.dependency_overrides[get_diagram_generator] = lambda: fakes["diagram_generator"]
    app.dependency_overrides[get_validator] = lambda: fakes["validator"]

    return TestClient(app)


def test_start_run_creates_a_session_and_returns_requirements(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    fakes["requirements_analyzer"].analyze.return_value = make_requirements()
    fakes["artifact_store"].save.return_value = "dev/x/requirements/v1.json"

    response = client.post("/requirements-runs", json={"input": "Build a todo app."})

    assert response.status_code == 201
    body = response.json()
    assert body["stage"] == "requirements"
    assert body["requirements_version"] == 1
    assert body["requirements"]["summary"] == "A todo app."
    fakes["store"].create.assert_called_once()


def test_get_run_returns_404_when_session_missing(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    fakes["store"].get.return_value = None

    response = client.get("/requirements-runs/does-not-exist")

    assert response.status_code == 404


def test_get_run_returns_the_stored_record(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(
        session_id="abc-123",
        requirements_version=1,
        requirements=make_requirements(),
    )
    fakes["store"].get.return_value = record

    response = client.get("/requirements-runs/abc-123")

    assert response.status_code == 200
    assert response.json()["session_id"] == "abc-123"


def test_refine_run_rejects_when_stage_is_not_requirements(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(session_id="abc-123", stage="architecture")
    fakes["store"].get.return_value = record

    response = client.post(
        "/requirements-runs/abc-123/refine", json={"input": "Add auth."}
    )

    assert response.status_code == 409


def test_refine_run_bumps_the_version_and_persists(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(
        session_id="abc-123",
        requirements_version=1,
        requirements=make_requirements(),
    )
    fakes["store"].get.return_value = record
    fakes["requirements_analyzer"].analyze.return_value = make_requirements(
        summary="A refined todo app."
    )

    response = client.post(
        "/requirements-runs/abc-123/refine", json={"input": "Add auth."}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["requirements_version"] == 2
    assert body["requirements"]["summary"] == "A refined todo app."
    fakes["store"].upsert.assert_called_once()


def test_accept_run_rejects_when_no_requirements_yet(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(session_id="abc-123")
    fakes["store"].get.return_value = record

    response = client.post("/requirements-runs/abc-123/accept")

    assert response.status_code == 409


def test_accept_run_rejects_when_already_accepted(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(
        session_id="abc-123", stage="architecture", requirements=make_requirements()
    )
    fakes["store"].get.return_value = record

    response = client.post("/requirements-runs/abc-123/accept")

    assert response.status_code == 409


def test_accept_run_generates_and_persists_the_architecture(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(
        session_id="abc-123",
        requirements_version=1,
        requirements=make_requirements(),
    )
    fakes["store"].get.return_value = record
    fakes["design_analyzer"].analyze.return_value = make_design()
    fakes["validator"].validate.side_effect = lambda design: design
    fakes["diagram_generator"].generate.return_value = "<svg></svg>"
    fakes["artifact_store"].save_design_json.return_value = "dev/abc-123/design/v1.json"
    fakes["artifact_store"].save_design_svg.return_value = "dev/abc-123/design/v1.svg"

    # `record` is mutated in place across the route's two upsert() calls, so
    # inspecting fakes["store"].upsert.call_args_list *after* the request
    # would show the same (final) object twice — snapshot the stage at the
    # moment each upsert actually happens instead.
    stage_snapshots: list[str] = []

    def _snapshot_stage(r: SessionRecord) -> SessionRecord:
        stage_snapshots.append(r.stage)
        return r

    fakes["store"].upsert.side_effect = _snapshot_stage

    response = client.post("/requirements-runs/abc-123/accept")

    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "architecture"
    assert body["design_version"] == 1
    assert body["design"]["architecture_summary"] == "A simple design."
    # Once to mark the session "generating" before the expensive work starts,
    # once more to persist the finished "architecture" result.
    assert stage_snapshots == ["generating", "architecture"]


def test_accept_run_rejects_a_second_call_while_already_generating(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    """The narrowed double-submit guard: a session already marked
    "generating" (by a first accept call still in flight, or a prior one
    that crashed mid-generation) must reject a second accept immediately,
    without touching the analyzer/diagram generator/validator at all."""
    record = SessionRecord(
        session_id="abc-123",
        stage="generating",
        requirements=make_requirements(),
    )
    fakes["store"].get.return_value = record

    response = client.post("/requirements-runs/abc-123/accept")

    assert response.status_code == 409
    fakes["design_analyzer"].analyze.assert_not_called()
    fakes["store"].upsert.assert_not_called()


def test_accept_run_returns_422_and_reverts_stage_when_generation_fails(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(
        session_id="abc-123",
        requirements_version=1,
        requirements=make_requirements(),
    )
    fakes["store"].get.return_value = record
    fakes["design_analyzer"].analyze.side_effect = DesignGenerationWorkflowError("boom")

    stage_snapshots: list[str] = []

    def _snapshot_stage(r: SessionRecord) -> SessionRecord:
        stage_snapshots.append(r.stage)
        return r

    fakes["store"].upsert.side_effect = _snapshot_stage

    response = client.post("/requirements-runs/abc-123/accept")

    assert response.status_code == 422
    # Once to mark "generating", once to revert to "requirements" + set error
    # — a failed generation must not leave the session permanently stuck on
    # "generating", unable to ever retry accept.
    assert stage_snapshots == ["generating", "requirements"]
    assert record.error is not None


def test_accept_run_returns_409_when_a_concurrent_write_wins_the_race(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    """The ETag guard: if another request wrote to this session between our
    ``load_owned`` and the "generating" upsert (the sliver of the
    double-submit race the stage check alone can't close), Cosmos rejects
    our write with a conflict. That must surface as 409, and the expensive
    generation pipeline must never run."""
    record = SessionRecord(
        session_id="abc-123",
        requirements_version=1,
        requirements=make_requirements(),
    )
    fakes["store"].get.return_value = record
    fakes["store"].upsert.side_effect = SessionConflictError("conflict")

    response = client.post("/requirements-runs/abc-123/accept")

    assert response.status_code == 409
    fakes["design_analyzer"].analyze.assert_not_called()


def test_refine_run_returns_409_when_a_concurrent_write_wins_the_race(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(
        session_id="abc-123",
        requirements_version=1,
        requirements=make_requirements(),
    )
    fakes["store"].get.return_value = record
    fakes["requirements_analyzer"].analyze.return_value = make_requirements(
        summary="A refined todo app."
    )
    fakes["store"].upsert.side_effect = SessionConflictError("conflict")

    response = client.post(
        "/requirements-runs/abc-123/refine", json={"input": "Add auth."}
    )

    assert response.status_code == 409


def test_refine_architecture_rejects_when_stage_is_not_architecture(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(session_id="abc-123", stage="requirements")
    fakes["store"].get.return_value = record

    response = client.post(
        "/requirements-runs/abc-123/refine-architecture", json={"input": "Add caching."}
    )

    assert response.status_code == 409
    fakes["design_analyzer"].analyze.assert_not_called()


def test_refine_architecture_rejects_a_second_call_while_already_generating(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(
        session_id="abc-123",
        stage="generating",
        requirements=make_requirements(),
        design=make_design(),
    )
    fakes["store"].get.return_value = record

    response = client.post(
        "/requirements-runs/abc-123/refine-architecture", json={"input": "Add caching."}
    )

    assert response.status_code == 409
    fakes["design_analyzer"].analyze.assert_not_called()
    fakes["store"].upsert.assert_not_called()


def test_refine_architecture_bumps_the_version_and_persists(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(
        session_id="abc-123",
        stage="architecture",
        requirements_version=1,
        requirements=make_requirements(),
        design_version=1,
        design=make_design(),
    )
    fakes["store"].get.return_value = record
    fakes["design_analyzer"].analyze.return_value = make_design(
        architecture_summary="A refined design."
    )
    fakes["validator"].validate.side_effect = lambda design: design
    fakes["diagram_generator"].generate.return_value = "<svg></svg>"
    fakes["artifact_store"].save_design_json.return_value = "dev/abc-123/design/v2.json"
    fakes["artifact_store"].save_design_svg.return_value = "dev/abc-123/design/v2.svg"

    stage_snapshots: list[str] = []

    def _snapshot_stage(r: SessionRecord) -> SessionRecord:
        stage_snapshots.append(r.stage)
        return r

    fakes["store"].upsert.side_effect = _snapshot_stage

    response = client.post(
        "/requirements-runs/abc-123/refine-architecture", json={"input": "Add caching."}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "architecture"
    assert body["design_version"] == 2
    assert body["design"]["architecture_summary"] == "A refined design."
    # Once to mark "generating" before the expensive work starts, once more
    # to persist the refined result.
    assert stage_snapshots == ["generating", "architecture"]

    # The analyzer must have been called with the previous design as context
    # (the original, pre-refinement design), not asked to generate a fresh
    # architecture from scratch.
    _, call_kwargs = fakes["design_analyzer"].analyze.call_args
    assert call_kwargs["previous_design"] == make_design()
    assert call_kwargs["refinement_input"] == "Add caching."


def test_refine_architecture_rejects_when_no_architecture_yet(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(
        session_id="abc-123", stage="architecture", requirements=make_requirements()
    )
    fakes["store"].get.return_value = record

    response = client.post(
        "/requirements-runs/abc-123/refine-architecture", json={"input": "Add caching."}
    )

    assert response.status_code == 409


def test_refine_architecture_returns_422_and_reverts_stage_when_generation_fails(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(
        session_id="abc-123",
        stage="architecture",
        requirements=make_requirements(),
        design_version=1,
        design=make_design(),
    )
    fakes["store"].get.return_value = record
    fakes["design_analyzer"].analyze.side_effect = DesignGenerationWorkflowError("boom")

    stage_snapshots: list[str] = []

    def _snapshot_stage(r: SessionRecord) -> SessionRecord:
        stage_snapshots.append(r.stage)
        return r

    fakes["store"].upsert.side_effect = _snapshot_stage

    response = client.post(
        "/requirements-runs/abc-123/refine-architecture", json={"input": "Add caching."}
    )

    assert response.status_code == 422
    # Once to mark "generating", once to revert to "architecture" (not
    # "requirements" — the previous design is still valid) + set error.
    assert stage_snapshots == ["generating", "architecture"]
    assert record.error is not None


def test_list_runs_returns_empty_when_caller_is_anonymous(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    """With AUTH_ENABLED=false, owner_oid is always None, so this must
    return [] rather than every session anyone has ever created — it must
    not fall back to listing everything."""
    response = client.get("/requirements-runs")

    assert response.status_code == 200
    assert response.json() == []
    fakes["store"].list_for_owner.assert_not_called()


def test_list_runs_returns_the_store_results_for_an_authenticated_owner(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    with patch(
        "app.api.routes.requirements.owner_fields",
        return_value=("owner-oid-1", "Some User"),
    ):
        fakes["store"].list_for_owner.return_value = [
            SessionRecord(session_id="abc-123", owner_oid="owner-oid-1"),
            SessionRecord(session_id="def-456", owner_oid="owner-oid-1"),
        ]

        response = client.get("/requirements-runs")

    assert response.status_code == 200
    body = response.json()
    assert [r["session_id"] for r in body] == ["abc-123", "def-456"]
    fakes["store"].list_for_owner.assert_called_once_with("owner-oid-1")
