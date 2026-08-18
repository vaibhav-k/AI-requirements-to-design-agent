from __future__ import annotations

import uuid
from collections.abc import Iterator
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
from app.infrastructure.session_store import SessionRecord
from app.models import RequirementsArtifact, StoredArtifact
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


def make_stored_artifact_json(**requirement_overrides: object) -> str:
    """The exact envelope ArtifactStore.save persists — see
    app/api/routes/requirements.py's _persist_requirements_blob."""
    stored = StoredArtifact(
        artifact_id=str(uuid.uuid4()),
        session_id="abc-123",
        artifact_type="requirements",
        version=1,
        created_at="2026-01-01T00:00:00+00:00",
        source_text="Build a todo app.",
        requirements=make_requirements(**requirement_overrides),
    )
    return stored.model_dump_json()


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
def client(fakes: dict[str, MagicMock]) -> Iterator[TestClient]:
    """A ``TestClient`` with ``AUTH_ENABLED=false`` — every ``require_role``/
    ``require_user``/ownership check is a no-op. See
    ``test_requirements_routes.py``'s identical fixture for why all three
    ``get_settings`` bindings (``app.web.main``, ``app.security.auth``,
    ``app.api.ownership``) need patching, not just the one used at app
    construction — a single patch there only "worked" by coincidence
    whenever the real, unpatched environment also defaulted to
    ``AUTH_ENABLED=false``.
    """
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

    auth_patcher = patch("app.security.auth.get_settings", return_value=settings)
    ownership_patcher = patch("app.api.ownership.get_settings", return_value=settings)
    auth_patcher.start()
    ownership_patcher.start()
    try:
        yield TestClient(app)
    finally:
        auth_patcher.stop()
        ownership_patcher.stop()


def own_session(fakes: dict[str, MagicMock]) -> None:
    """Make load_owned succeed for session "abc-123" — every route here
    checks ownership before touching artifact content, same as the
    session routes."""
    fakes["store"].get.return_value = SessionRecord(session_id="abc-123")


# ---------------------------------------------------------------------
# Ownership gating — every route below must 404 the same way get_run does
# ---------------------------------------------------------------------


def test_requirements_versions_404s_when_session_missing(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    fakes["store"].get.return_value = None

    response = client.get("/requirements-runs/abc-123/requirements/versions")

    assert response.status_code == 404
    fakes["artifact_store"].list_requirements_versions.assert_not_called()


# ---------------------------------------------------------------------
# Requirements versions
# ---------------------------------------------------------------------


def test_list_requirements_versions_returns_the_stores_list(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    own_session(fakes)
    fakes["artifact_store"].list_requirements_versions.return_value = [1, 2, 3]

    response = client.get("/requirements-runs/abc-123/requirements/versions")

    assert response.status_code == 200
    assert response.json() == [1, 2, 3]
    fakes["artifact_store"].list_requirements_versions.assert_called_once_with(
        "abc-123"
    )


def test_get_requirements_version_returns_the_unwrapped_artifact(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    own_session(fakes)
    fakes[
        "artifact_store"
    ].get_requirements_json.return_value = make_stored_artifact_json(
        summary="v1 summary"
    )

    response = client.get("/requirements-runs/abc-123/requirements/1")

    assert response.status_code == 200
    assert response.json()["summary"] == "v1 summary"
    fakes["artifact_store"].get_requirements_json.assert_called_once_with("abc-123", 1)


def test_get_requirements_version_404s_when_not_stored(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    own_session(fakes)
    fakes["artifact_store"].get_requirements_json.return_value = None

    response = client.get("/requirements-runs/abc-123/requirements/99")

    assert response.status_code == 404


def test_get_requirements_version_500s_on_malformed_content(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    own_session(fakes)
    fakes["artifact_store"].get_requirements_json.return_value = "{not valid json"

    response = client.get("/requirements-runs/abc-123/requirements/1")

    assert response.status_code == 500


# ---------------------------------------------------------------------
# Architecture versions
# ---------------------------------------------------------------------


def test_list_architecture_versions_returns_the_stores_list(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    own_session(fakes)
    fakes["artifact_store"].list_design_versions.return_value = [1]

    response = client.get("/requirements-runs/abc-123/architecture/versions")

    assert response.status_code == 200
    assert response.json() == [1]
    fakes["artifact_store"].list_design_versions.assert_called_once_with("abc-123")


def test_get_architecture_version_returns_the_design(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    own_session(fakes)
    fakes[
        "artifact_store"
    ].get_design_json.return_value = '{"architecture_summary": "A design."}'

    response = client.get("/requirements-runs/abc-123/architecture/1")

    assert response.status_code == 200
    assert response.json()["architecture_summary"] == "A design."
    fakes["artifact_store"].get_design_json.assert_called_once_with("abc-123", 1)


def test_get_architecture_version_404s_when_not_stored(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    own_session(fakes)
    fakes["artifact_store"].get_design_json.return_value = None

    response = client.get("/requirements-runs/abc-123/architecture/99")

    assert response.status_code == 404


# ---------------------------------------------------------------------
# Architecture comparison
# ---------------------------------------------------------------------


def test_compare_architecture_versions_returns_a_structured_diff(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    own_session(fakes)
    fakes["artifact_store"].get_design_json.side_effect = [
        '{"architecture_summary": "Original.", "components": '
        '[{"id": "C-001", "name": "API", "responsibility": "Handles requests."}]}',
        '{"architecture_summary": "Refined.", "components": '
        '[{"id": "C-001", "name": "API", '
        '"responsibility": "Handles requests and auth."}]}',
    ]

    response = client.get("/requirements-runs/abc-123/architecture/compare?from=1&to=2")

    assert response.status_code == 200
    body = response.json()
    assert body["from_version"] == 1
    assert body["to_version"] == 2
    assert body["architecture_summary_changed"] is True
    assert body["from_architecture_summary"] == "Original."
    assert body["to_architecture_summary"] == "Refined."
    assert len(body["components"]["changed"]) == 1
    assert (
        body["components"]["changed"][0]["before"]["responsibility"]
        == "Handles requests."
    )
    assert fakes["artifact_store"].get_design_json.call_args_list == [
        (("abc-123", 1),),
        (("abc-123", 2),),
    ]


def test_compare_architecture_versions_404s_when_from_version_missing(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    own_session(fakes)
    fakes["artifact_store"].get_design_json.return_value = None

    response = client.get(
        "/requirements-runs/abc-123/architecture/compare?from=99&to=1"
    )

    assert response.status_code == 404


def test_compare_architecture_versions_404s_when_session_missing(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    fakes["store"].get.return_value = None

    response = client.get("/requirements-runs/abc-123/architecture/compare?from=1&to=2")

    assert response.status_code == 404
    fakes["artifact_store"].get_design_json.assert_not_called()


def test_get_architecture_diagram_returns_svg(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    own_session(fakes)
    fakes["artifact_store"].get_design_svg.return_value = "<svg>test</svg>"

    response = client.get("/requirements-runs/abc-123/architecture/1/diagram")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.text == "<svg>test</svg>"
    fakes["artifact_store"].get_design_svg.assert_called_once_with("abc-123", 1)


def test_get_architecture_diagram_404s_when_not_stored(
    client: TestClient, fakes: dict[str, MagicMock]
) -> None:
    own_session(fakes)
    fakes["artifact_store"].get_design_svg.return_value = None

    response = client.get("/requirements-runs/abc-123/architecture/99/diagram")

    assert response.status_code == 404
