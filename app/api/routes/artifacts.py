"""HTTP endpoints for reading persisted artifact *content* by version.

``app/api/routes/requirements.py`` exposes the session's *current* state
(``RequirementsRunView`` — latest requirements, latest design, and the
Blob *paths* of the persisted JSON/SVG). It never returns older versions or
the artifacts' actual bytes. This module is the read side of that gap: a
UI that wants to show version history, diff two versions, or render the
architecture diagram needs to fetch specific past versions' real content
from Blob Storage — never fabricate it.

Every route here still goes through ``load_owned`` first, exactly like the
session routes: a session's artifact history is only visible to whoever
may see the session itself. Every route also requires one of the three
functional App Roles (``Depends(require_role(*_ANY_ROLE))`` — Admin passes
automatically, see ``app/security/auth.py``'s RBAC section): reading
artifact history is available to any role, unlike the write routes in
``app/api/routes/requirements.py``, which are gated per-action.

* ``GET /requirements-runs/{id}/requirements/versions``
  — version numbers, oldest first.
* ``GET /requirements-runs/{id}/requirements/{version}``
  — that version's ``RequirementsArtifact``.
* ``GET /requirements-runs/{id}/architecture/versions``
  — version numbers, oldest first.
* ``GET /requirements-runs/{id}/architecture/{version}``
  — that version's ``SystemDesignArtifact``.
* ``GET /requirements-runs/{id}/architecture/{version}/diagram``
  — that version's SVG diagram markup.
* ``GET /requirements-runs/{id}/architecture/compare``
  — a structured, backend-computed diff between two architecture versions.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import ValidationError

from app.api.dependencies import get_artifact_store, get_session_store
from app.api.ownership import load_owned
from app.application.ports import ArtifactStorePort, SessionStorePort
from app.design.comparison import ArchitectureComparison, compare_architectures
from app.domain.design import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact, StoredArtifact
from app.security.auth import ROLE_ARCHITECT, ROLE_REVIEWER, ROLE_USER, require_role

# Every route in this router needs the exact same role check — any of the
# three functional roles (Admin passes automatically, see
# `app/security/auth.py`) — unlike `requirements.py`, where each route is
# gated on a different role, so it's applied once here at router
# construction (`dependencies=`) rather than repeated on every `@router.get`.
_ANY_ROLE = (ROLE_USER, ROLE_ARCHITECT, ROLE_REVIEWER)

router = APIRouter(
    prefix="/requirements-runs",
    tags=["artifacts"],
    dependencies=[Depends(require_role(*_ANY_ROLE))],
)


def _not_found(kind: str, version: int) -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND,
        f"No {kind} version {version} is stored for this session.",
    )


def _malformed(kind: str, version: int) -> HTTPException:
    # Should not happen against data this app itself wrote, but a stored
    # blob is still external input from the route's perspective — fail
    # with a clear 500 rather than let a ValidationError escape unhandled.
    return HTTPException(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        f"Stored {kind} version {version} could not be parsed.",
    )


@router.get(
    "/{session_id}/requirements/versions",
)
def list_requirements_versions(
    session_id: str,
    request: Request,
    store: Annotated[SessionStorePort, Depends(get_session_store)],  # noqa: B008
    artifact_store: Annotated[
        ArtifactStorePort, Depends(get_artifact_store)
    ],  # noqa: B008
) -> list[int]:
    load_owned(store, session_id, request)
    return artifact_store.list_requirements_versions(session_id)


@router.get(
    "/{session_id}/requirements/{version}",
)
def get_requirements_version(
    session_id: str,
    version: int,
    request: Request,
    store: Annotated[SessionStorePort, Depends(get_session_store)],  # noqa: B008
    artifact_store: Annotated[
        ArtifactStorePort, Depends(get_artifact_store)
    ],  # noqa: B008
) -> RequirementsArtifact:
    load_owned(store, session_id, request)

    content = artifact_store.get_requirements_json(session_id, version)
    if content is None:
        raise _not_found("requirements", version)

    try:
        return StoredArtifact.model_validate_json(content).requirements
    except ValidationError as exc:
        raise _malformed("requirements", version) from exc


@router.get(
    "/{session_id}/architecture/versions",
)
def list_architecture_versions(
    session_id: str,
    request: Request,
    store: Annotated[SessionStorePort, Depends(get_session_store)],  # noqa: B008
    artifact_store: Annotated[
        ArtifactStorePort, Depends(get_artifact_store)
    ],  # noqa: B008
) -> list[int]:
    load_owned(store, session_id, request)
    return artifact_store.list_design_versions(session_id)


def _load_architecture_version(
    artifact_store: ArtifactStorePort,
    session_id: str,
    version: int,
) -> SystemDesignArtifact:
    """Shared by `get_architecture_version` and `compare_architecture_versions`
    so both 404/500 the same way for the same missing/malformed version."""

    content = artifact_store.get_design_json(session_id, version)
    if content is None:
        raise _not_found("architecture", version)

    try:
        return SystemDesignArtifact.model_validate_json(content)
    except ValidationError as exc:
        raise _malformed("architecture", version) from exc


@router.get(
    "/{session_id}/architecture/compare",
)
def compare_architecture_versions(
    session_id: str,
    request: Request,
    from_version: Annotated[int, Query(alias="from")],
    to_version: Annotated[int, Query(alias="to")],
    store: Annotated[SessionStorePort, Depends(get_session_store)],  # noqa: B008
    artifact_store: Annotated[
        ArtifactStorePort, Depends(get_artifact_store)
    ],  # noqa: B008
) -> ArchitectureComparison:
    """A structured diff between two persisted architecture versions.

    The frontend already computes this client-side (`VersionBar`/`DiffList`
    fetch both full versions and diff in the browser — see
    `frontend/src/lib/diff.ts`); this is the backend equivalent, for any
    client that wants the diff without fetching both full artifacts and
    re-implementing the comparison itself. `?from=`/`?to=` are plain
    version numbers, same as the `{version}` path parameter below — this is
    a query-parameterized sibling of it, not a new versioning scheme.

    Registered *before* `/{session_id}/architecture/{version}` below: since
    that path parameter has no explicit `:int` route convertor, Starlette's
    router matches it against any path segment (including the literal
    string "compare") before FastAPI's own int coercion ever runs, which
    would otherwise 422 instead of resolving to this route. FastAPI/
    Starlette match routes in registration order, so the literal path must
    come first.
    """
    load_owned(store, session_id, request)

    before = _load_architecture_version(artifact_store, session_id, from_version)
    after = _load_architecture_version(artifact_store, session_id, to_version)

    return compare_architectures(from_version, to_version, before, after)


@router.get(
    "/{session_id}/architecture/{version}",
)
def get_architecture_version(
    session_id: str,
    version: int,
    request: Request,
    store: Annotated[SessionStorePort, Depends(get_session_store)],  # noqa: B008
    artifact_store: Annotated[
        ArtifactStorePort, Depends(get_artifact_store)
    ],  # noqa: B008
) -> SystemDesignArtifact:
    load_owned(store, session_id, request)
    return _load_architecture_version(artifact_store, session_id, version)


@router.get("/{session_id}/architecture/{version}/diagram")
def get_architecture_diagram(
    session_id: str,
    version: int,
    request: Request,
    store: Annotated[SessionStorePort, Depends(get_session_store)],  # noqa: B008
    artifact_store: Annotated[
        ArtifactStorePort, Depends(get_artifact_store)
    ],  # noqa: B008
) -> Response:
    load_owned(store, session_id, request)

    svg = artifact_store.get_design_svg(session_id, version)
    if svg is None:
        raise _not_found("diagram", version)

    return Response(content=svg, media_type="image/svg+xml")
