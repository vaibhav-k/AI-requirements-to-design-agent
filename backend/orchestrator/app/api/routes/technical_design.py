"""HTTP endpoints for the fifth (and final) pipeline stage: the technical
design document.

The requirements -> architecture -> work breakdown flow
(``app/api/routes/requirements.py``, ``app/api/routes/work_breakdown.py``)
stops at an approved work breakdown. This module picks up from there,
mirroring the same "Accept / Refine" loop shape one stage later:

* ``POST /requirements-runs/{id}/technical-design``
  - compile a technical design document from the session's current
  requirements + architecture + work breakdown. Only possible once the
  session is in the ``"work_breakdown"`` stage - ``409`` otherwise, same
  as ``_require_stage`` everywhere else in this pipeline. ``409`` again
  if a document already exists for this session (use ``refine`` instead).
  Unlike ``generate_work_breakdown``, this stage has no separate
  "approved" gate to check first - a work breakdown reaching this stage
  at all already implies it exists; nothing else needs a prior approval
  the way a work breakdown needs an approved architecture.
* ``POST /requirements-runs/{id}/technical-design/refine``
  - refine an existing document with new input, the technical-design
  analogue of ``refine-work-breakdown``. ``409`` unless a document
  already exists.
* ``GET /requirements-runs/{id}/technical-design``
  - the current (latest) document. ``404`` if none has been generated yet.
* ``GET /requirements-runs/{id}/technical-design/versions``
  - version numbers, oldest first.
* ``GET /requirements-runs/{id}/technical-design/export``
  - the current document rendered to ``.docx``
  (``application/vnd.openxmlformats-officedocument.wordprocessingml.document``),
  via ``DocumentExporterPort``, with the approved architecture diagram
  embedded.
* ``GET /requirements-runs/{id}/technical-design/{version}``
  - that version's ``TechnicalDesignArtifact``.

Every route requires ``load_owned`` first (see
``app/api/routes/requirements.py``'s identical rule) and a role check:
generating/refining needs ``Architect`` (the same role every other
generate/refine route in this pipeline needs), every read route accepts
any of the three functional roles, same as
``app/api/routes/work_breakdown.py``.
"""

from __future__ import annotations

import base64
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ValidationError

from app.api.dependencies import (
    TechnicalDesignExportDependencies,
    TechnicalDesignGenerationDependencies,
    get_artifact_store,
    get_session_store,
    get_technical_design_export_dependencies,
    get_technical_design_generation_dependencies,
)
from app.api.ownership import load_owned
from app.api.routes.requirements import (
    STAGE_GENERATING,
    RequirementsRunView,
    _require_stage,
    _upsert_guarded,
)
from app.api.routes.work_breakdown import STAGE_WORK_BREAKDOWN
from app.application.errors import (
    TechnicalDesignExportError,
    TechnicalDesignGenerationError,
)
from app.application.ports import ArtifactStorePort, SessionStorePort
from app.domain.session import SessionRecord
from app.domain.technical_design import TechnicalDesignArtifact
from app.infrastructure.sync_bridge import run_sync
from app.security.auth import ROLE_ARCHITECT, ROLE_REVIEWER, ROLE_USER, require_role

router = APIRouter(prefix="/requirements-runs", tags=["technical-design"])

# Same "any of the three functional roles" shape as
# `app/api/routes/work_breakdown.py`'s `_ANY_ROLE`.
_ANY_ROLE = (ROLE_USER, ROLE_ARCHITECT, ROLE_REVIEWER)

# The stage this session moves into on a successful generate/refine -
# named once, matching STAGE_WORK_BREAKDOWN/STAGE_ARCHITECTURE elsewhere
# in this pipeline. `STAGE_GENERATING` (imported above) is the shared
# placeholder stage every generate/refine route in this pipeline moves
# into first, as a double-submit guard.
STAGE_TECHNICAL_DESIGN = "technical_design"

_DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


class RefineTechnicalDesignRequest(BaseModel):
    input: str


def _revert_after_failure(
    store: SessionStorePort, record: SessionRecord, stage: str, error: str
) -> None:
    """Shared by generate/refine: revert `stage` and record `error` after a
    failed generation - the technical-design analogue of
    ``app/api/routes/work_breakdown.py``'s identical helper."""
    record.stage = stage
    record.error = error
    _upsert_guarded(store, record)


@router.post(
    "/{session_id}/technical-design",
    dependencies=[Depends(require_role(ROLE_ARCHITECT))],
)
def generate_technical_design(
    session_id: str,
    request: Request,
    store: Annotated[SessionStorePort, Depends(get_session_store)],
    deps: Annotated[
        TechnicalDesignGenerationDependencies,
        Depends(get_technical_design_generation_dependencies),
    ],
) -> RequirementsRunView:
    record = load_owned(store, session_id, request)

    _require_stage(
        record,
        STAGE_WORK_BREAKDOWN,
        f"This session is in stage {record.stage!r}; generating a "
        f"technical design document is only possible once it's in "
        f"{STAGE_WORK_BREAKDOWN!r}.",
    )
    if (
        record.requirements is None
        or record.design is None
        or record.work_breakdown is None
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This session has no requirements/architecture/work breakdown "
            "to build a technical design document from yet.",
        )
    if record.technical_design_version != 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A technical design document already exists for this "
            "session; use refine instead.",
        )

    # Same double-submit guard as every other generate/refine route in
    # this pipeline: mark "generating" before the expensive work starts,
    # conditional on the ETag this record was loaded with.
    record.stage = STAGE_GENERATING
    _upsert_guarded(store, record)

    try:
        result = run_sync(
            deps.session_use_case.execute(
                session_id=record.session_id,
                version=record.technical_design_version,
                requirements=record.requirements,
                design=record.design,
                work_breakdown=record.work_breakdown,
            ),
            caller="generate_technical_design",
        )
    except (ValueError, TechnicalDesignGenerationError) as exc:
        # Revert to "work_breakdown" (still valid and still what's
        # persisted) rather than leave the session stuck mid-generation.
        _revert_after_failure(store, record, STAGE_WORK_BREAKDOWN, str(exc))
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    record.stage = STAGE_TECHNICAL_DESIGN
    record.technical_design_version = result.version
    record.technical_design = result.document
    record.technical_design_blob = result.document_blob
    record.error = None

    _upsert_guarded(store, record)
    return RequirementsRunView.from_record(record)


@router.post(
    "/{session_id}/technical-design/refine",
    dependencies=[Depends(require_role(ROLE_ARCHITECT))],
)
def refine_technical_design(
    session_id: str,
    body: RefineTechnicalDesignRequest,
    request: Request,
    store: Annotated[SessionStorePort, Depends(get_session_store)],
    deps: Annotated[
        TechnicalDesignGenerationDependencies,
        Depends(get_technical_design_generation_dependencies),
    ],
) -> RequirementsRunView:
    record = load_owned(store, session_id, request)

    _require_stage(
        record,
        STAGE_TECHNICAL_DESIGN,
        f"This session is in stage {record.stage!r}; refining a technical "
        f"design document is only possible once it's in "
        f"{STAGE_TECHNICAL_DESIGN!r}.",
    )
    if (
        record.requirements is None
        or record.design is None
        or record.work_breakdown is None
        or record.technical_design is None
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This session has no technical design document to refine yet.",
        )

    record.stage = STAGE_GENERATING
    _upsert_guarded(store, record)

    try:
        result = run_sync(
            deps.session_use_case.execute(
                session_id=record.session_id,
                version=record.technical_design_version,
                requirements=record.requirements,
                design=record.design,
                work_breakdown=record.work_breakdown,
                previous_document=record.technical_design,
                refinement_input=body.input,
            ),
            caller="refine_technical_design",
        )
    except (ValueError, TechnicalDesignGenerationError) as exc:
        _revert_after_failure(store, record, STAGE_TECHNICAL_DESIGN, str(exc))
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    record.stage = STAGE_TECHNICAL_DESIGN
    record.technical_design_version = result.version
    record.technical_design = result.document
    record.technical_design_blob = result.document_blob
    record.error = None

    _upsert_guarded(store, record)
    return RequirementsRunView.from_record(record)


@router.get(
    "/{session_id}/technical-design",
    dependencies=[Depends(require_role(*_ANY_ROLE))],
)
def get_technical_design(
    session_id: str,
    request: Request,
    store: Annotated[SessionStorePort, Depends(get_session_store)],
) -> TechnicalDesignArtifact:
    record = load_owned(store, session_id, request)

    if record.technical_design is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No technical design document has been generated for this session yet.",
        )

    return record.technical_design


@router.get(
    "/{session_id}/technical-design/versions",
    dependencies=[Depends(require_role(*_ANY_ROLE))],
)
def list_technical_design_versions(
    session_id: str,
    request: Request,
    store: Annotated[SessionStorePort, Depends(get_session_store)],
    artifact_store: Annotated[ArtifactStorePort, Depends(get_artifact_store)],
) -> list[int]:
    load_owned(store, session_id, request)
    return artifact_store.list_technical_design_versions(session_id)


@router.get(
    "/{session_id}/technical-design/export",
    dependencies=[Depends(require_role(*_ANY_ROLE))],
)
def export_technical_design(
    session_id: str,
    request: Request,
    store: Annotated[SessionStorePort, Depends(get_session_store)],
    deps: Annotated[
        TechnicalDesignExportDependencies,
        Depends(get_technical_design_export_dependencies),
    ],
) -> Response:
    """Render the session's current technical design document to
    ``.docx``, with the approved architecture diagram embedded.

    Registered before ``/{session_id}/technical-design/{version}`` below -
    same "literal path segments must come first" reasoning as
    ``app/api/routes/work_breakdown.py``'s ``export_work_breakdown``.
    """
    record = load_owned(store, session_id, request)

    if (
        record.requirements is None
        or record.design is None
        or record.work_breakdown is None
        or record.technical_design is None
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This session has no technical design document to export yet.",
        )

    try:
        result = deps.session_use_case.execute(
            session_id=record.session_id,
            version=record.technical_design_version,
            document=record.technical_design,
            design=record.design,
            requirements=record.requirements,
            work_breakdown=record.work_breakdown,
        )
    except TechnicalDesignExportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    # Stamp the pointer onto the session record - same "cheap, re-derivable
    # cache" reasoning as `app/api/routes/work_breakdown.py`'s
    # `export_work_breakdown`; a lost race here only costs the stamp, never
    # the export, since the `.docx` bytes are already durably persisted by
    # `deps.session_use_case.execute` above regardless.
    record.technical_design_export_blob = result.export_blob
    _upsert_guarded(store, record)

    docx_bytes = base64.b64decode(result.export.docx_base64)
    filename = result.export.filename or "technical-design.docx"

    return Response(
        content=docx_bytes,
        media_type=_DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/{session_id}/technical-design/{version}",
    dependencies=[Depends(require_role(*_ANY_ROLE))],
)
def get_technical_design_version(
    session_id: str,
    version: int,
    request: Request,
    store: Annotated[SessionStorePort, Depends(get_session_store)],
    artifact_store: Annotated[ArtifactStorePort, Depends(get_artifact_store)],
) -> TechnicalDesignArtifact:
    load_owned(store, session_id, request)

    content = artifact_store.get_technical_design_json(session_id, version)
    if content is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No technical design version {version} is stored for this session.",
        )

    try:
        return TechnicalDesignArtifact.model_validate_json(content)
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Stored technical design version {version} could not be parsed.",
        ) from exc
