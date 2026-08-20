"""HTTP endpoints for the fourth pipeline stage: work breakdown.

The requirements -> architecture flow (``app/api/routes/requirements.py``)
stops at an approved architecture. This module picks up from there,
mirroring that same "Accept / Refine" loop shape one stage later:

* ``POST /requirements-runs/{id}/work-breakdown``
  - generate a Feature -> Story -> Task breakdown from the session's
  current requirements + architecture. Only possible once the session is
  in the ``"architecture"`` stage *and* its current design has been
  ``approve``d (see ``app/api/routes/requirements.py``'s ``approve_run``)
  - ``409`` otherwise, the same "clear error instead of silently allowing
  it" shape ``_require_stage`` already gives every other out-of-order call
  in this pipeline. ``409`` again if a breakdown already exists for this
  session (use ``refine`` instead).
* ``POST /requirements-runs/{id}/work-breakdown/refine``
  - refine an existing breakdown with new input, the work-breakdown
  analogue of ``refine-architecture``. ``409`` unless a breakdown already
  exists.
* ``GET /requirements-runs/{id}/work-breakdown``
  - the current (latest) breakdown. ``404`` if none has been generated yet.
* ``GET /requirements-runs/{id}/work-breakdown/versions``
  - version numbers, oldest first.
* ``GET /requirements-runs/{id}/work-breakdown/{version}``
  - that version's ``WorkBreakdownArtifact``.
* ``GET /requirements-runs/{id}/work-breakdown/export``
  - the current breakdown validated and rendered to CSV
  (``text/csv``), via ``WorkBreakdownExporterPort``.

Every route requires ``load_owned`` first (see
``app/api/routes/requirements.py``'s identical rule) and a role check:
generating/refining needs ``Architect`` (the same role that generates/
refines the architecture this breakdown traces back to), every read route
accepts any of the three functional roles, same as
``app/api/routes/artifacts.py``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ValidationError

from app.api.dependencies import (
    WorkBreakdownExportDependencies,
    WorkBreakdownGenerationDependencies,
    get_artifact_store,
    get_session_store,
    get_work_breakdown_export_dependencies,
    get_work_breakdown_generation_dependencies,
)
from app.api.ownership import load_owned
from app.api.routes.requirements import (
    APPROVAL_APPROVED,
    STAGE_ARCHITECTURE,
    STAGE_GENERATING,
    RequirementsRunView,
    _require_stage,
    _upsert_guarded,
)
from app.application.errors import (
    WorkBreakdownExportError,
    WorkBreakdownGenerationError,
)
from app.application.ports import ArtifactStorePort, SessionStorePort
from app.domain.session import SessionRecord
from app.domain.work_breakdown import WorkBreakdownArtifact
from app.infrastructure.sync_bridge import run_sync
from app.security.auth import ROLE_ARCHITECT, ROLE_REVIEWER, ROLE_USER, require_role

router = APIRouter(prefix="/requirements-runs", tags=["work-breakdown"])

# Same "any of the three functional roles" shape as
# `app/api/routes/artifacts.py`'s `_ANY_ROLE` - every read route here
# accepts it, unlike the generate/refine routes, which are gated to
# `ROLE_ARCHITECT` alone.
_ANY_ROLE = (ROLE_USER, ROLE_ARCHITECT, ROLE_REVIEWER)

# The stage this session moves into on a successful generate/refine -
# named once rather than repeated as a literal, matching STAGE_REQUIREMENTS/
# STAGE_GENERATING/STAGE_ARCHITECTURE in app/api/routes/requirements.py.
STAGE_WORK_BREAKDOWN = "work_breakdown"


class RefineWorkBreakdownRequest(BaseModel):
    input: str


def _require_architecture_approved(record: SessionRecord) -> None:
    """Raise 409 unless the session's *current* architecture has been
    approved - a work breakdown has nothing settled to trace back to
    otherwise. Mirrors ``_require_stage``'s "clear error instead of
    silently allowing it" shape for a condition that isn't itself a stage.
    """
    if record.approval_status != APPROVAL_APPROVED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This session's architecture must be approved before "
            "generating a work breakdown.",
        )


def _revert_after_failure(
    store: SessionStorePort, record: SessionRecord, stage: str, error: str
) -> None:
    """Shared by generate/refine: revert `stage` and record `error` after a
    failed generation, the same "never leave the session stuck on
    'generating'" rule ``accept_run``/``refine_architecture`` already
    apply."""
    record.stage = stage
    record.error = error
    _upsert_guarded(store, record)


@router.post(
    "/{session_id}/work-breakdown",
    dependencies=[Depends(require_role(ROLE_ARCHITECT))],
)
def generate_work_breakdown(
    session_id: str,
    request: Request,
    store: Annotated[SessionStorePort, Depends(get_session_store)],
    deps: Annotated[
        WorkBreakdownGenerationDependencies,
        Depends(get_work_breakdown_generation_dependencies),
    ],
) -> RequirementsRunView:
    record = load_owned(store, session_id, request)

    _require_stage(
        record,
        STAGE_ARCHITECTURE,
        f"This session is in stage {record.stage!r}; generating a work "
        f"breakdown is only possible once it's in {STAGE_ARCHITECTURE!r}.",
    )
    _require_architecture_approved(record)
    if record.requirements is None or record.design is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This session has no requirements/architecture to build a "
            "work breakdown from yet.",
        )
    if record.work_breakdown_version != 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A work breakdown already exists for this session; use "
            "refine instead.",
        )

    # Same double-submit guard as accept_run/refine_architecture: mark
    # "generating" before the expensive work starts, conditional on the
    # ETag this record was loaded with.
    record.stage = STAGE_GENERATING
    _upsert_guarded(store, record)

    try:
        result = run_sync(
            deps.session_use_case.execute(
                session_id=record.session_id,
                version=record.work_breakdown_version,
                requirements=record.requirements,
                design=record.design,
            ),
            caller="generate_work_breakdown",
        )
    except (ValueError, WorkBreakdownGenerationError) as exc:
        # Revert to "architecture" (not "requirements") - the approved
        # architecture is still valid and still what's persisted; only the
        # work breakdown generation failed.
        _revert_after_failure(store, record, STAGE_ARCHITECTURE, str(exc))
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    record.stage = STAGE_WORK_BREAKDOWN
    record.work_breakdown_version = result.version
    record.work_breakdown = result.breakdown
    record.work_breakdown_blob = result.breakdown_blob
    record.error = None

    _upsert_guarded(store, record)
    return RequirementsRunView.from_record(record)


@router.post(
    "/{session_id}/work-breakdown/refine",
    dependencies=[Depends(require_role(ROLE_ARCHITECT))],
)
def refine_work_breakdown(
    session_id: str,
    body: RefineWorkBreakdownRequest,
    request: Request,
    store: Annotated[SessionStorePort, Depends(get_session_store)],
    deps: Annotated[
        WorkBreakdownGenerationDependencies,
        Depends(get_work_breakdown_generation_dependencies),
    ],
) -> RequirementsRunView:
    record = load_owned(store, session_id, request)

    _require_stage(
        record,
        STAGE_WORK_BREAKDOWN,
        f"This session is in stage {record.stage!r}; refining a work "
        f"breakdown is only possible once it's in {STAGE_WORK_BREAKDOWN!r}.",
    )
    if (
        record.requirements is None
        or record.design is None
        or record.work_breakdown is None
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This session has no work breakdown to refine yet.",
        )

    record.stage = STAGE_GENERATING
    _upsert_guarded(store, record)

    try:
        result = run_sync(
            deps.session_use_case.execute(
                session_id=record.session_id,
                version=record.work_breakdown_version,
                requirements=record.requirements,
                design=record.design,
                previous_breakdown=record.work_breakdown,
                refinement_input=body.input,
            ),
            caller="refine_work_breakdown",
        )
    except (ValueError, WorkBreakdownGenerationError) as exc:
        # Revert to "work_breakdown" (the previous breakdown is still valid
        # and still what's persisted) rather than leave the session stuck
        # on "generating".
        _revert_after_failure(store, record, STAGE_WORK_BREAKDOWN, str(exc))
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    record.stage = STAGE_WORK_BREAKDOWN
    record.work_breakdown_version = result.version
    record.work_breakdown = result.breakdown
    record.work_breakdown_blob = result.breakdown_blob
    record.error = None

    _upsert_guarded(store, record)
    return RequirementsRunView.from_record(record)


@router.get(
    "/{session_id}/work-breakdown",
    dependencies=[Depends(require_role(*_ANY_ROLE))],
)
def get_work_breakdown(
    session_id: str,
    request: Request,
    store: Annotated[SessionStorePort, Depends(get_session_store)],
) -> WorkBreakdownArtifact:
    record = load_owned(store, session_id, request)

    if record.work_breakdown is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No work breakdown has been generated for this session yet.",
        )

    return record.work_breakdown


@router.get(
    "/{session_id}/work-breakdown/versions",
    dependencies=[Depends(require_role(*_ANY_ROLE))],
)
def list_work_breakdown_versions(
    session_id: str,
    request: Request,
    store: Annotated[SessionStorePort, Depends(get_session_store)],
    artifact_store: Annotated[ArtifactStorePort, Depends(get_artifact_store)],
) -> list[int]:
    load_owned(store, session_id, request)
    return artifact_store.list_work_breakdown_versions(session_id)


@router.get(
    "/{session_id}/work-breakdown/export",
    dependencies=[Depends(require_role(*_ANY_ROLE))],
)
def export_work_breakdown(
    session_id: str,
    request: Request,
    store: Annotated[SessionStorePort, Depends(get_session_store)],
    deps: Annotated[
        WorkBreakdownExportDependencies,
        Depends(get_work_breakdown_export_dependencies),
    ],
) -> Response:
    """Validate the session's current work breakdown and render it to CSV.

    Registered before ``/{session_id}/work-breakdown/{version}`` below -
    same "literal path segments must come first" reasoning as
    ``app/api/routes/artifacts.py``'s ``compare_architecture_versions``,
    since that path parameter has no ``:int`` route convertor.
    """
    record = load_owned(store, session_id, request)

    if (
        record.requirements is None
        or record.design is None
        or record.work_breakdown is None
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This session has no work breakdown to export yet.",
        )

    try:
        result = deps.session_use_case.execute(
            session_id=record.session_id,
            version=record.work_breakdown_version,
            breakdown=record.work_breakdown,
            requirements=record.requirements,
            design=record.design,
        )
    except WorkBreakdownExportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    # Stamp the pointer onto the session record - see
    # `SessionRecord.work_breakdown_export_blob`'s docstring - so a caller
    # can later tell "this version was already exported" without a
    # separate round trip to Blob Storage. Same `_upsert_guarded` path
    # every other mutating route in this file uses; the CSV itself is
    # already durably persisted either way (an overwriting, re-computable
    # cache - see `ArtifactStorePort.save_work_breakdown_csv`), so a lost
    # race here only costs the stamp, never the export.
    record.work_breakdown_export_blob = result.export_blob
    _upsert_guarded(store, record)

    return Response(content=result.export.csv_text, media_type="text/csv")


@router.get(
    "/{session_id}/work-breakdown/{version}",
    dependencies=[Depends(require_role(*_ANY_ROLE))],
)
def get_work_breakdown_version(
    session_id: str,
    version: int,
    request: Request,
    store: Annotated[SessionStorePort, Depends(get_session_store)],
    artifact_store: Annotated[ArtifactStorePort, Depends(get_artifact_store)],
) -> WorkBreakdownArtifact:
    load_owned(store, session_id, request)

    content = artifact_store.get_work_breakdown_json(session_id, version)
    if content is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No work breakdown version {version} is stored for this session.",
        )

    try:
        return WorkBreakdownArtifact.model_validate_json(content)
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Stored work breakdown version {version} could not be parsed.",
        ) from exc
