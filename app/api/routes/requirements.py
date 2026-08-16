"""HTTP endpoints for the requirements → architecture flow.

Mirrors the CLI's ``DesignSession``/``ArchitectureSession`` loop
(``app/main.py``) as stateless HTTP calls backed by
:class:`~app.infrastructure.session_store.SessionRecord`:

* ``POST /requirements-runs``          — like the CLI's first ``analyze()`` call.
* ``GET  /requirements-runs``          — list the caller's own sessions.
* ``GET  /requirements-runs/{id}``     — poll/resume a session.
* ``POST /requirements-runs/{id}/refine``         — like choosing "2. Refine".
* ``POST /requirements-runs/{id}/accept``         — like choosing "1. Accept".
* ``POST /requirements-runs/{id}/refine-architecture`` — refine an
  already-accepted architecture with new input; no CLI equivalent exists
  yet (the CLI's loop only refines requirements, not architecture).

Every route requires ``load_owned`` before touching a record, so one caller
can never read or mutate another caller's session (see ``app/api/ownership.py``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.analyzer import RequirementsAnalyzer
from app.api.dependencies import (
    get_artifact_store,
    get_design_analyzer,
    get_diagram_generator,
    get_requirements_analyzer,
    get_session_store,
    get_validator,
)
from app.api.ownership import load_owned, owner_fields
from app.design.analyzer import SystemDesignAnalyzer
from app.design.diagram import ArchitectureDiagramGenerator
from app.design.models import SystemDesignArtifact
from app.design.session import ArchitectureSession, DesignGenerationWorkflowError
from app.design.validator import ArchitectureValidator
from app.infrastructure.session_store import (
    SessionConflictError,
    SessionRecord,
    SessionStore,
)
from app.models import RequirementsArtifact, StoredArtifact
from app.storage import ArtifactStore

# Route paths are relative to this prefix, set once here instead of repeated
# as a literal on every @router decorator below (SonarQube S1192: string
# literals should not be duplicated).
router = APIRouter(prefix="/requirements-runs", tags=["requirements"])

# Session lifecycle stages, named once so every comparison/assignment below
# reads as "what stage" instead of a bare, typo-prone string literal.
STAGE_REQUIREMENTS = "requirements"
STAGE_GENERATING = "generating"
STAGE_ARCHITECTURE = "architecture"


class StartRunRequest(BaseModel):
    input: str


class RefineRunRequest(BaseModel):
    input: str


class RefineArchitectureRequest(BaseModel):
    input: str


class RequirementsRunView(BaseModel):
    session_id: str
    stage: str
    requirements_version: int
    requirements: RequirementsArtifact | None
    design_version: int
    design: SystemDesignArtifact | None
    design_blob: str | None
    diagram_blob: str | None
    error: str | None

    @classmethod
    def from_record(cls, record: SessionRecord) -> RequirementsRunView:
        return cls(
            session_id=record.session_id,
            stage=record.stage,
            requirements_version=record.requirements_version,
            requirements=record.requirements,
            design_version=record.design_version,
            design=record.design,
            design_blob=record.design_blob,
            diagram_blob=record.diagram_blob,
            error=record.error,
        )


def _persist_requirements_blob(
    artifact_store: ArtifactStore,
    record: SessionRecord,
    source_text: str,
) -> str:
    stored = StoredArtifact(
        artifact_id=str(uuid.uuid4()),
        session_id=record.session_id,
        artifact_type="requirements",
        version=record.requirements_version,
        created_at=datetime.now(UTC).isoformat(),
        source_text=source_text,
        requirements=record.requirements,  # type: ignore[arg-type]
    )
    return artifact_store.save(stored)


def _require_stage(record: SessionRecord, expected: str, conflict_detail: str) -> None:
    """Raise 409 if ``record`` isn't in ``expected`` stage; no-op otherwise.

    Shared by every route that must reject an out-of-order call (refine
    after accept, accept twice, etc.) so the check and its error response
    live in one place rather than being copy-pasted per route.
    """
    if record.stage != expected:
        raise HTTPException(status.HTTP_409_CONFLICT, conflict_detail)


def _upsert_guarded(store: SessionStore, record: SessionRecord) -> SessionRecord:
    """``store.upsert()``, turning a lost ETag race into an HTTP 409.

    Every call site here loaded ``record`` via ``load_owned``/``store.get()``
    first, so it carries the ETag of the version it read. If another
    request wrote to this session in between — the remaining sliver of the
    double-submit race the ``"generating"`` stage alone doesn't close, see
    ``accept_run`` — Cosmos rejects this write (``SessionConflictError``,
    from a 412 response) instead of one request silently clobbering the
    other's change.
    """
    try:
        return store.upsert(record)
    except SessionConflictError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This session was modified by another request at the same "
            "time; reload it and retry.",
        ) from exc


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=RequirementsRunView,
)
def start_run(
    body: StartRunRequest,
    request: Request,
    store: SessionStore = Depends(get_session_store),  # noqa: B008
    artifact_store: ArtifactStore = Depends(get_artifact_store),  # noqa: B008
    analyzer: RequirementsAnalyzer = Depends(get_requirements_analyzer),  # noqa: B008
) -> RequirementsRunView:
    owner_oid, owner_name = owner_fields(request)

    record = SessionRecord(
        session_id=str(uuid.uuid4()),
        owner_oid=owner_oid,
        owner_name=owner_name,
        source_text=body.input,
    )

    record.requirements_version = 1
    record.requirements = analyzer.analyze(user_input=body.input)
    record.requirements_blob = _persist_requirements_blob(
        artifact_store, record, body.input
    )

    store.create(record)
    return RequirementsRunView.from_record(record)


@router.get(
    "",
    response_model=list[RequirementsRunView],
)
def list_runs(
    request: Request,
    store: SessionStore = Depends(get_session_store),  # noqa: B008
) -> list[RequirementsRunView]:
    """The caller's own sessions, newest first.

    With ``AUTH_ENABLED=false`` (or an anonymous caller), ``owner_fields``
    returns ``(None, None)`` — every session created locally is unowned —
    so this always returns ``[]`` rather than every session anyone has ever
    started. That matches ``SessionStore.list_for_owner``'s own "unowned
    records are nobody's" behavior; it isn't a separate special case here.
    """
    owner_oid, _ = owner_fields(request)
    records = store.list_for_owner(owner_oid) if owner_oid else []
    return [RequirementsRunView.from_record(record) for record in records]


@router.get(
    "/{session_id}",
    response_model=RequirementsRunView,
)
def get_run(
    session_id: str,
    request: Request,
    store: SessionStore = Depends(get_session_store),  # noqa: B008
) -> RequirementsRunView:
    record = load_owned(store, session_id, request)
    return RequirementsRunView.from_record(record)


@router.post(
    "/{session_id}/refine",
    response_model=RequirementsRunView,
)
def refine_run(
    session_id: str,
    body: RefineRunRequest,
    request: Request,
    store: SessionStore = Depends(get_session_store),  # noqa: B008
    artifact_store: ArtifactStore = Depends(get_artifact_store),  # noqa: B008
    analyzer: RequirementsAnalyzer = Depends(get_requirements_analyzer),  # noqa: B008
) -> RequirementsRunView:
    record = load_owned(store, session_id, request)

    _require_stage(
        record,
        STAGE_REQUIREMENTS,
        f"This session is in stage {record.stage!r}; "
        f"refining is only possible while still in {STAGE_REQUIREMENTS!r}.",
    )

    record.requirements_version += 1
    record.source_text = body.input
    record.requirements = analyzer.analyze(
        user_input=body.input,
        previous_artifact=record.requirements,
    )
    record.requirements_blob = _persist_requirements_blob(
        artifact_store, record, body.input
    )

    _upsert_guarded(store, record)
    return RequirementsRunView.from_record(record)


@router.post(
    "/{session_id}/accept",
    response_model=RequirementsRunView,
)
def accept_run(
    session_id: str,
    request: Request,
    store: SessionStore = Depends(get_session_store),  # noqa: B008
    artifact_store: ArtifactStore = Depends(get_artifact_store),  # noqa: B008
    analyzer: SystemDesignAnalyzer = Depends(get_design_analyzer),  # noqa: B008
    diagram_generator: ArchitectureDiagramGenerator = Depends(  # noqa: B008
        get_diagram_generator
    ),
    validator: ArchitectureValidator = Depends(get_validator),  # noqa: B008
) -> RequirementsRunView:
    record = load_owned(store, session_id, request)

    _require_stage(
        record,
        STAGE_REQUIREMENTS,
        f"This session is in stage {record.stage!r}; it has already "
        "been accepted, or is currently being generated by another "
        "request.",
    )
    if record.requirements is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This session has no requirements to accept yet.",
        )

    # Mark the session as being processed *before* the expensive work below
    # (AI generation + validation + diagram render + two Blob writes) starts.
    # This upsert is conditional on the ETag `record` was loaded with (see
    # `_upsert_guarded`/`CosmosSessionStore.upsert`), so if two concurrent
    # accept calls both pass the stage check above, only the first writer
    # here wins — the second gets a 409 instead of silently racing the first
    # through generation against the same session.
    record.stage = STAGE_GENERATING
    _upsert_guarded(store, record)

    design_session = ArchitectureSession(
        analyzer=analyzer,
        diagram_generator=diagram_generator,
        validator=validator,
        store=artifact_store,
        session_id=record.session_id,
    )

    try:
        result = design_session.generate(record.requirements)
    except DesignGenerationWorkflowError as exc:
        # Revert to "requirements" (not left stuck on "generating") so the
        # caller can retry accept — a failed generation must not permanently
        # lock the session.
        record.stage = STAGE_REQUIREMENTS
        record.error = str(exc)
        _upsert_guarded(store, record)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    record.stage = STAGE_ARCHITECTURE
    record.design_version = result.version
    record.design = result.design
    record.design_blob = result.design_blob
    record.diagram_blob = result.diagram_blob
    record.error = None

    _upsert_guarded(store, record)
    return RequirementsRunView.from_record(record)


@router.post(
    "/{session_id}/refine-architecture",
    response_model=RequirementsRunView,
)
def refine_architecture(
    session_id: str,
    body: RefineArchitectureRequest,
    request: Request,
    store: SessionStore = Depends(get_session_store),  # noqa: B008
    artifact_store: ArtifactStore = Depends(get_artifact_store),  # noqa: B008
    analyzer: SystemDesignAnalyzer = Depends(get_design_analyzer),  # noqa: B008
    diagram_generator: ArchitectureDiagramGenerator = Depends(  # noqa: B008
        get_diagram_generator
    ),
    validator: ArchitectureValidator = Depends(get_validator),  # noqa: B008
) -> RequirementsRunView:
    """Refine an already-accepted architecture with new input.

    The architecture analogue of ``refine_run``: unlike ``accept_run``
    (which only fires once, from ``STAGE_REQUIREMENTS``), this can be called
    repeatedly once a session has reached ``STAGE_ARCHITECTURE``, each call
    producing a new design version built on top of the previous one rather
    than starting from scratch — see ``SystemDesignAnalyzer.analyze``'s
    ``previous_design``/``refinement_input`` parameters.
    """
    record = load_owned(store, session_id, request)

    _require_stage(
        record,
        STAGE_ARCHITECTURE,
        f"This session is in stage {record.stage!r}; refining an "
        f"architecture is only possible once it's in {STAGE_ARCHITECTURE!r}.",
    )
    if record.requirements is None or record.design is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This session has no architecture to refine yet.",
        )

    # Same double-submit guard as accept_run: mark "generating" before the
    # expensive work starts, conditional on the ETag this record was loaded
    # with, so a second concurrent refine call gets a 409 instead of racing
    # this one through generation against the same session.
    record.stage = STAGE_GENERATING
    _upsert_guarded(store, record)

    design_session = ArchitectureSession(
        analyzer=analyzer,
        diagram_generator=diagram_generator,
        validator=validator,
        store=artifact_store,
        session_id=record.session_id,
        version=record.design_version,
    )

    try:
        result = design_session.generate(
            record.requirements,
            previous_design=record.design,
            refinement_input=body.input,
        )
    except DesignGenerationWorkflowError as exc:
        # Revert to "architecture" (the previous design is still valid and
        # still what's persisted) rather than leave the session stuck on
        # "generating" — a failed refinement must not block retrying it, or
        # block viewing the architecture that already existed.
        record.stage = STAGE_ARCHITECTURE
        record.error = str(exc)
        _upsert_guarded(store, record)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    record.stage = STAGE_ARCHITECTURE
    record.design_version = result.version
    record.design = result.design
    record.design_blob = result.design_blob
    record.diagram_blob = result.diagram_blob
    record.error = None

    _upsert_guarded(store, record)
    return RequirementsRunView.from_record(record)
