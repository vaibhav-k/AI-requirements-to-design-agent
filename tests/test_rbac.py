"""RBAC (Entra ID App Roles) tests for the requirements/artifacts routers.

Every other route test file (`test_requirements_routes.py`,
`test_artifacts_routes.py`) runs with `AUTH_ENABLED=false`, where
`require_role` is a no-op — deliberately, so those files stay focused on
route *logic* rather than authorization. This file is the complement: it
turns auth on, injects a bearer token with a chosen set of App Roles (via
a patched `decode_token`, exactly like `test_web_main.py`'s
`test_me_returns_claims_when_token_valid`), and checks the role gate on
each route plus the ownership bypass for `Admin` (see
`app/api/ownership.py`'s `is_admin`).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_artifact_store,
    get_design_analyzer,
    get_diagram_generator,
    get_document_extractor,
    get_requirements_analyzer,
    get_session_store,
    get_validator,
)
from app.config import Settings
from app.design.models import SystemDesignArtifact
from app.infrastructure.session_store import SessionRecord
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
        "document_extractor": MagicMock(),
    }


@pytest.fixture
def rbac_app(fakes: dict[str, MagicMock]) -> Iterator[TestClient]:
    """A ``TestClient`` with ``AUTH_ENABLED=true`` and every external
    dependency faked. ``get_settings`` is patched at both the
    app-construction and per-request layers (``app.security.auth`` and
    ``app.api.ownership`` each import their own bound name), mirroring
    ``test_web_main.py``'s ``make_app`` — both patches are torn down after
    the test via the ``finally`` block below.
    """
    settings = Settings(
        auth_enabled=True,
        entra_tenant_id="tenant-123",
        entra_client_id="client-456",
    )
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
    app.dependency_overrides[get_document_extractor] = lambda: fakes[
        "document_extractor"
    ]

    settings_patcher = patch("app.security.auth.get_settings", return_value=settings)
    settings_patcher.start()
    ownership_patcher = patch("app.api.ownership.get_settings", return_value=settings)
    ownership_patcher.start()

    client = TestClient(app)
    try:
        yield client
    finally:
        settings_patcher.stop()
        ownership_patcher.stop()


def auth_headers(roles: list[str], oid: str = "caller-1") -> dict[str, str]:
    # `roles`/`oid` aren't read from the header — `with_claims` patches
    # `decode_token` directly to return them — this just needs *some*
    # bearer token present so `require_user` doesn't 401 before the role
    # check even runs.
    return {"Authorization": "Bearer a.b.c"}


def with_claims(roles: list[str], oid: str = "caller-1") -> Any:
    """Patch ``decode_token`` to return a token with the given App Roles."""
    return patch(
        "app.security.auth.decode_token",
        return_value={"oid": oid, "roles": roles},
    )


# --------------------------------------------------------------------------- #
# start_run — requires User
# --------------------------------------------------------------------------- #


def test_start_run_allowed_for_user_role(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    fakes["requirements_analyzer"].analyze.return_value = make_requirements()
    fakes["artifact_store"].save.return_value = "blob"

    with with_claims(["User"]):
        response = rbac_app.post(
            "/requirements-runs",
            json={"input": "Build a todo app."},
            headers=auth_headers(["User"]),
        )

    assert response.status_code == 201


def test_start_run_rejected_for_reviewer_only(rbac_app: TestClient) -> None:
    with with_claims(["Reviewer"]):
        response = rbac_app.post(
            "/requirements-runs",
            json={"input": "Build a todo app."},
            headers=auth_headers(["Reviewer"]),
        )

    assert response.status_code == 403


def test_start_run_rejected_for_no_roles_at_all(rbac_app: TestClient) -> None:
    """A valid, authenticated caller with zero App Roles assigned is
    rejected outright — per the explicit product decision to 403 rather
    than default such a caller into a baseline role."""
    with with_claims([]):
        response = rbac_app.post(
            "/requirements-runs",
            json={"input": "Build a todo app."},
            headers=auth_headers([]),
        )

    assert response.status_code == 403


def test_start_run_allowed_for_admin_role(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    fakes["requirements_analyzer"].analyze.return_value = make_requirements()
    fakes["artifact_store"].save.return_value = "blob"

    with with_claims(["Admin"]):
        response = rbac_app.post(
            "/requirements-runs",
            json={"input": "Build a todo app."},
            headers=auth_headers(["Admin"]),
        )

    assert response.status_code == 201


# --------------------------------------------------------------------------- #
# accept_run / refine_architecture — require Architect
# --------------------------------------------------------------------------- #


def test_accept_run_rejected_for_user_role(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(
        session_id="abc-123",
        owner_oid="caller-1",
        requirements_version=1,
        requirements=make_requirements(),
    )
    fakes["store"].get.return_value = record

    with with_claims(["User"], oid="caller-1"):
        response = rbac_app.post(
            "/requirements-runs/abc-123/accept",
            headers=auth_headers(["User"], oid="caller-1"),
        )

    assert response.status_code == 403


def test_accept_run_allowed_for_architect_role(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(
        session_id="abc-123",
        owner_oid="caller-1",
        requirements_version=1,
        requirements=make_requirements(),
    )
    fakes["store"].get.return_value = record
    fakes["design_analyzer"].analyze.return_value = make_design()
    fakes["validator"].validate.side_effect = lambda design: design
    fakes["diagram_generator"].generate.return_value = "<svg></svg>"
    fakes["artifact_store"].save_design_json.return_value = "blob.json"
    fakes["artifact_store"].save_design_svg.return_value = "blob.svg"

    with with_claims(["Architect"], oid="caller-1"):
        response = rbac_app.post(
            "/requirements-runs/abc-123/accept",
            headers=auth_headers(["Architect"], oid="caller-1"),
        )

    assert response.status_code == 200
    assert response.json()["stage"] == "architecture"


# --------------------------------------------------------------------------- #
# approve_run / reject_run — require Reviewer
# --------------------------------------------------------------------------- #


def test_approve_run_rejected_for_architect_role(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(
        session_id="abc-123",
        owner_oid="caller-1",
        stage="architecture",
        design=make_design(),
    )
    fakes["store"].get.return_value = record

    with with_claims(["Architect"], oid="caller-1"):
        response = rbac_app.post(
            "/requirements-runs/abc-123/approve",
            json={},
            headers=auth_headers(["Architect"], oid="caller-1"),
        )

    assert response.status_code == 403


def test_approve_run_allowed_for_reviewer_role(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(
        session_id="abc-123",
        owner_oid="caller-1",
        stage="architecture",
        design=make_design(),
    )
    fakes["store"].get.return_value = record

    with with_claims(["Reviewer"], oid="caller-1"):
        response = rbac_app.post(
            "/requirements-runs/abc-123/approve",
            json={},
            headers=auth_headers(["Reviewer"], oid="caller-1"),
        )

    assert response.status_code == 200
    assert response.json()["approval_status"] == "approved"


# --------------------------------------------------------------------------- #
# Reads — any of User/Architect/Reviewer (Admin implicit)
# --------------------------------------------------------------------------- #


def test_get_run_allowed_for_any_functional_role(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(session_id="abc-123", owner_oid="caller-1")
    fakes["store"].get.return_value = record

    with with_claims(["Reviewer"], oid="caller-1"):
        response = rbac_app.get(
            "/requirements-runs/abc-123",
            headers=auth_headers(["Reviewer"], oid="caller-1"),
        )

    assert response.status_code == 200


def test_get_run_rejected_for_no_roles(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(session_id="abc-123", owner_oid="caller-1")
    fakes["store"].get.return_value = record

    with with_claims([], oid="caller-1"):
        response = rbac_app.get(
            "/requirements-runs/abc-123",
            headers=auth_headers([], oid="caller-1"),
        )

    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# Admin ownership bypass — Admin can act on someone else's session
# --------------------------------------------------------------------------- #


def test_get_run_returns_404_for_a_non_admin_reading_someone_elses_session(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(session_id="abc-123", owner_oid="someone-else")
    fakes["store"].get.return_value = record

    with with_claims(["User"], oid="caller-1"):
        response = rbac_app.get(
            "/requirements-runs/abc-123",
            headers=auth_headers(["User"], oid="caller-1"),
        )

    assert response.status_code == 404


def test_admin_can_read_someone_elses_session(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(session_id="abc-123", owner_oid="someone-else")
    fakes["store"].get.return_value = record

    with with_claims(["Admin"], oid="caller-1"):
        response = rbac_app.get(
            "/requirements-runs/abc-123",
            headers=auth_headers(["Admin"], oid="caller-1"),
        )

    assert response.status_code == 200
    assert response.json()["session_id"] == "abc-123"


def test_list_runs_returns_every_session_for_an_admin(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    fakes["store"].list_all.return_value = [
        SessionRecord(session_id="abc-123", owner_oid="owner-a"),
        SessionRecord(session_id="def-456", owner_oid="owner-b"),
    ]

    with with_claims(["Admin"], oid="admin-1"):
        response = rbac_app.get(
            "/requirements-runs",
            headers=auth_headers(["Admin"], oid="admin-1"),
        )

    assert response.status_code == 200
    body = response.json()
    assert [r["session_id"] for r in body] == ["abc-123", "def-456"]
    fakes["store"].list_all.assert_called_once()
    fakes["store"].list_for_owner.assert_not_called()


def test_list_runs_returns_only_own_sessions_for_a_non_admin(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    fakes["store"].list_for_owner.return_value = [
        SessionRecord(session_id="abc-123", owner_oid="caller-1"),
    ]

    with with_claims(["User"], oid="caller-1"):
        response = rbac_app.get(
            "/requirements-runs",
            headers=auth_headers(["User"], oid="caller-1"),
        )

    assert response.status_code == 200
    body = response.json()
    assert [r["session_id"] for r in body] == ["abc-123"]
    fakes["store"].list_for_owner.assert_called_once_with("caller-1")
    fakes["store"].list_all.assert_not_called()


# --------------------------------------------------------------------------- #
# Artifacts router — any of User/Architect/Reviewer, Admin bypasses ownership
# --------------------------------------------------------------------------- #


def test_list_requirements_versions_rejected_for_no_roles(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(session_id="abc-123", owner_oid="caller-1")
    fakes["store"].get.return_value = record

    with with_claims([], oid="caller-1"):
        response = rbac_app.get(
            "/requirements-runs/abc-123/requirements/versions",
            headers=auth_headers([], oid="caller-1"),
        )

    assert response.status_code == 403


def test_list_requirements_versions_allowed_for_reviewer(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(session_id="abc-123", owner_oid="caller-1")
    fakes["store"].get.return_value = record
    fakes["artifact_store"].list_requirements_versions.return_value = [1, 2]

    with with_claims(["Reviewer"], oid="caller-1"):
        response = rbac_app.get(
            "/requirements-runs/abc-123/requirements/versions",
            headers=auth_headers(["Reviewer"], oid="caller-1"),
        )

    assert response.status_code == 200
    assert response.json() == [1, 2]


# --------------------------------------------------------------------------- #
# rename_run — any functional role, own session; Admin bypasses ownership
# --------------------------------------------------------------------------- #


def test_rename_run_allowed_for_any_functional_role(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(session_id="abc-123", owner_oid="caller-1")
    fakes["store"].get.return_value = record

    with with_claims(["Reviewer"], oid="caller-1"):
        response = rbac_app.post(
            "/requirements-runs/abc-123/rename",
            json={"name": "Checkout revamp"},
            headers=auth_headers(["Reviewer"], oid="caller-1"),
        )

    assert response.status_code == 200
    assert response.json()["name"] == "Checkout revamp"
    fakes["store"].upsert.assert_called_once()


def test_rename_run_rejected_for_no_roles(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(session_id="abc-123", owner_oid="caller-1")
    fakes["store"].get.return_value = record

    with with_claims([], oid="caller-1"):
        response = rbac_app.post(
            "/requirements-runs/abc-123/rename",
            json={"name": "Checkout revamp"},
            headers=auth_headers([], oid="caller-1"),
        )

    assert response.status_code == 403
    fakes["store"].upsert.assert_not_called()


def test_rename_run_returns_404_for_a_non_admin_renaming_someone_elses_session(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(session_id="abc-123", owner_oid="someone-else")
    fakes["store"].get.return_value = record

    with with_claims(["User"], oid="caller-1"):
        response = rbac_app.post(
            "/requirements-runs/abc-123/rename",
            json={"name": "Not mine"},
            headers=auth_headers(["User"], oid="caller-1"),
        )

    assert response.status_code == 404
    fakes["store"].upsert.assert_not_called()


def test_admin_can_rename_someone_elses_session(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(session_id="abc-123", owner_oid="someone-else")
    fakes["store"].get.return_value = record

    with with_claims(["Admin"], oid="admin-1"):
        response = rbac_app.post(
            "/requirements-runs/abc-123/rename",
            json={"name": "Relabeled by admin"},
            headers=auth_headers(["Admin"], oid="admin-1"),
        )

    assert response.status_code == 200
    assert response.json()["name"] == "Relabeled by admin"


def test_rename_run_rejects_empty_name(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    record = SessionRecord(session_id="abc-123", owner_oid="caller-1")
    fakes["store"].get.return_value = record

    with with_claims(["User"], oid="caller-1"):
        response = rbac_app.post(
            "/requirements-runs/abc-123/rename",
            json={"name": "   "},
            headers=auth_headers(["User"], oid="caller-1"),
        )

    assert response.status_code == 422
    fakes["store"].upsert.assert_not_called()


def test_list_runs_for_an_admin_includes_owner_name(
    rbac_app: TestClient, fakes: dict[str, MagicMock]
) -> None:
    fakes["store"].list_all.return_value = [
        SessionRecord(session_id="abc-123", owner_oid="owner-a", owner_name="Alice"),
    ]

    with with_claims(["Admin"], oid="admin-1"):
        response = rbac_app.get(
            "/requirements-runs",
            headers=auth_headers(["Admin"], oid="admin-1"),
        )

    assert response.status_code == 200
    assert response.json()[0]["owner_name"] == "Alice"
