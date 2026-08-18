"""HTTP endpoints for the requirements → architecture flow.

Mirrors the CLI's ``DesignSession``/``ArchitectureSession`` loop
(``app/main.py``) as stateless HTTP calls backed by
:class:`~app.infrastructure.session_store.SessionRecord`:

* ``POST /requirements-runs``          — like the CLI's first ``analyze()`` call.
* ``POST /requirements-runs/upload``   — same, but from an uploaded document
  (PDF/DOCX/PNG/JPG/JPEG/TXT) instead of typed text; see ``app/ingestion.py``.
* ``GET  /requirements-runs``          — list the caller's own sessions.
* ``GET  /requirements-runs/{id}``     — poll/resume a session.
* ``POST /requirements-runs/{id}/refine``         — like choosing "2. Refine".
* ``POST /requirements-runs/{id}/refine/upload``  — same, from an uploaded
  document.
* ``POST /requirements-runs/{id}/accept``         — like choosing "1. Accept".
* ``POST /requirements-runs/{id}/refine-architecture`` — refine an
  already-accepted architecture with new input; no CLI equivalent exists
  yet (the CLI's loop only refines requirements, not architecture).
* ``POST /requirements-runs/{id}/approve`` — record an "approved" decision
  against the current architecture version.
* ``POST /requirements-runs/{id}/reject`` — record a "rejected" decision
  against the current architecture version; does not block further
  ``refine-architecture`` calls.
* ``GET  /requirements-runs/{id}/source-file`` — download the original
  uploaded file for the current requirements version, if any.

Every route requires ``load_owned`` before touching a record, so one caller
can never read or mutate another caller's session (see ``app/api/ownership.py``),
*and* a role check (``Depends(require_role(...))``, see
``app/security/auth.py``) before that: creating/refining requirements needs
``User``, accepting/refining an architecture needs ``Architect``,
approving/rejecting needs ``Reviewer``, and every read route accepts any of
the three plus ``Reviewer``. ``Admin`` passes every check and additionally
bypasses ownership — see the README's "RBAC" section for the full matrix
and why (both checks are no-ops with ``AUTH_ENABLED=false``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel

from app.analyzer import RequirementsAnalyzer
from app.api.dependencies import (
    ArchitectureGenerationDependencies,
    ImageUploadDependencies,
    RequirementsUploadDependencies,
    get_architecture_generation_dependencies,
    get_artifact_store,
    get_image_upload_dependencies,
    get_requirements_analyzer,
    get_requirements_upload_dependencies,
    get_session_store,
)
from app.api.ownership import is_admin, load_owned, owner_fields
from app.design.models import ApprovalDecision, SystemDesignArtifact
from app.design.session import ArchitectureSession, DesignGenerationWorkflowError
from app.infrastructure.session_store import (
    SessionConflictError,
    SessionRecord,
    SessionStore,
)
from app.ingestion import (
    SUPPORTED_EXTENSIONS,
    DocumentExtractionError,
    RequirementsDocumentExtractor,
    is_image_filename,
    is_supported_filename,
)
from app.models import RequirementsArtifact, StoredArtifact
from app.security.auth import ROLE_ARCHITECT, ROLE_REVIEWER, ROLE_USER, require_role
from app.storage import ArtifactStore
from app.vision import (
    DiagramImageInterpreter,
    DiagramInterpretationError,
    ImageClassificationError,
    ImageInputClassifier,
)

# Route paths are relative to this prefix, set once here instead of repeated
# as a literal on every @router decorator below (SonarQube S1192: string
# literals should not be duplicated).
router = APIRouter(prefix="/requirements-runs", tags=["requirements"])

# Every read-only route accepts any of the three functional roles (plus
# Admin, which `require_role` always lets through regardless — see
# `app/security/auth.py`). Named once so "who can read" reads as a single
# concept rather than the same three-role tuple typed out at every read
# route's `Depends(require_role(...))`.
_ANY_ROLE = (ROLE_USER, ROLE_ARCHITECT, ROLE_REVIEWER)

# Session lifecycle stages, named once so every comparison/assignment below
# reads as "what stage" instead of a bare, typo-prone string literal.
STAGE_REQUIREMENTS = "requirements"
STAGE_GENERATING = "generating"
STAGE_ARCHITECTURE = "architecture"

# Approval decision states — see `SessionRecord.approval_status`.
APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"
APPROVAL_REJECTED = "rejected"


class StartRunRequest(BaseModel):
    input: str


class RefineRunRequest(BaseModel):
    input: str


class RefineArchitectureRequest(BaseModel):
    input: str


class ApprovalDecisionRequest(BaseModel):
    reason: str | None = None


class RenameRunRequest(BaseModel):
    name: str


MAX_NAME_LENGTH = 200


class RequirementsRunView(BaseModel):
    session_id: str
    name: str | None
    owner_name: str | None
    """Who started this session — only ever meaningful to the caller when
    it's someone *else* (an Admin browsing every session via ``list_all``,
    see ``list_runs``); for a non-Admin caller every session they can see is
    already their own. Read-only here — only ``owner_fields``, at session
    creation, ever sets it.
    """
    stage: str
    requirements_version: int
    requirements: RequirementsArtifact | None
    source_filename: str | None
    design_version: int
    design: SystemDesignArtifact | None
    design_blob: str | None
    diagram_blob: str | None
    approval_status: str
    approval_history: list[ApprovalDecision]
    error: str | None

    @classmethod
    def from_record(cls, record: SessionRecord) -> RequirementsRunView:
        return cls(
            session_id=record.session_id,
            name=record.name,
            owner_name=record.owner_name,
            stage=record.stage,
            requirements_version=record.requirements_version,
            requirements=record.requirements,
            source_filename=record.source_filename,
            design_version=record.design_version,
            design=record.design,
            design_blob=record.design_blob,
            diagram_blob=record.diagram_blob,
            approval_status=record.approval_status,
            approval_history=record.approval_history,
            error=record.error,
        )


def _persist_requirements_blob(
    artifact_store: ArtifactStore,
    record: SessionRecord,
    source_text: str,
    source_filename: str | None = None,
) -> str:
    stored = StoredArtifact(
        artifact_id=str(uuid.uuid4()),
        session_id=record.session_id,
        artifact_type="requirements",
        version=record.requirements_version,
        created_at=datetime.now(UTC).isoformat(),
        source_text=source_text,
        requirements=record.requirements,  # type: ignore[arg-type]
        source_filename=source_filename,
    )
    return artifact_store.save(stored)


async def _read_upload_content(file: UploadFile) -> tuple[str, bytes]:
    """Validate an uploaded file's extension and non-emptiness, and return
    its filename and raw bytes — the common first step for every upload
    route, before either OCR extraction or (for an image) classification
    decides what to do with those bytes.
    """

    filename = file.filename or ""

    if not is_supported_filename(filename):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Unsupported file type for {filename!r}. Supported types: "
            f"{', '.join(sorted(SUPPORTED_EXTENSIONS))}.",
        )

    content = await file.read()

    if not content:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{filename!r} is empty.",
        )

    return filename, content


def _extract_text_from_bytes(
    filename: str,
    content: bytes,
    extractor: RequirementsDocumentExtractor,
) -> str:
    """OCR/plain-text extraction from already-read upload bytes — split out
    from :func:`_extract_text_from_upload` so the image-classification path
    below can reuse it without re-reading (and exhausting)
    ``UploadFile.read()`` a second time.
    """

    try:
        return extractor.extract(filename, content)
    except DocumentExtractionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


async def _extract_text_from_upload(
    file: UploadFile,
    extractor: RequirementsDocumentExtractor,
) -> tuple[str, bytes]:
    """Validate and extract text from an uploaded file.

    Shared by the ``/upload`` start and refine routes for every supported
    extension *except* an image classified as a diagram (see
    ``_resolve_image_upload`` below, which every image upload goes through
    instead) — a non-image upload always ends up here, and an image
    classified as a document screenshot ends up here too, just via
    ``_extract_text_from_bytes`` directly since its bytes were already read
    for classification.
    """

    filename, content = await _read_upload_content(file)
    text = _extract_text_from_bytes(filename, content, extractor)
    return text, content


async def _resolve_image_upload(
    file: UploadFile,
    extractor: RequirementsDocumentExtractor,
    classifier: ImageInputClassifier,
    diagram_interpreter: DiagramImageInterpreter,
    notes: str | None,
) -> tuple[str, bytes, str, SystemDesignArtifact | None]:
    """Classify an uploaded image and resolve it into either extracted text
    or a directly-interpreted design — see the module-level docstring's
    reference to ``app/vision.py`` for why an image needs this extra step
    that a PDF/DOCX/TXT upload doesn't.

    Returns ``(filename, content, text, design)``, where exactly one of
    ``text``/``design`` is populated depending on the classification: a
    ``"document"`` screenshot returns its OCR'd text with ``design=None``
    (the caller proceeds through the same requirements pipeline as any
    other upload); a ``"diagram"`` returns ``text=""`` and the interpreted
    ``SystemDesignArtifact`` (the caller jumps straight to architecture —
    see ``_apply_diagram_to_record``).
    """

    filename, content = await _read_upload_content(file)

    try:
        classification = await classifier.classify_async(content, filename)
    except ImageClassificationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    if classification.kind == "diagram":
        try:
            design = await diagram_interpreter.interpret_async(
                content, filename, notes=notes
            )
        except DiagramInterpretationError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)
            ) from exc
        return filename, content, "", design

    text = _extract_text_from_bytes(filename, content, extractor)
    return filename, content, text, None


def _stub_requirements_from_diagram(
    design: SystemDesignArtifact,
) -> RequirementsArtifact:
    """A minimal ``RequirementsArtifact`` for a session whose architecture
    came directly from an uploaded diagram image rather than typed or
    OCR'd requirements text.

    Keeps ``RequirementsRunView.requirements`` non-null — so the
    Requirements tab isn't blank and ``requirements_version``/
    ``requirements_blob`` stay meaningful — without inventing functional
    requirements, actors, or constraints this project has no actual basis
    for; those lists stay empty rather than guessed at from the diagram.
    """

    return RequirementsArtifact(
        summary=(
            "Derived from an uploaded system design diagram rather than "
            f"typed requirements. {design.architecture_summary}"
        ),
        business_goal=(
            "Not specified — this session started from a diagram upload "
            "instead of typed requirements."
        ),
        actors=[],
        functional_requirements=[],
        non_functional_requirements=[],
        data_requirements=[],
        integration_requirements=[],
        constraints=[],
        assumptions=[],
        open_questions=[],
    )


def _apply_diagram_to_record(
    record: SessionRecord,
    filename: str,
    content: bytes,
    design: SystemDesignArtifact,
    image_deps: ImageUploadDependencies,
) -> None:
    """Mutate ``record`` in place to move it straight to
    :data:`STAGE_ARCHITECTURE` from an interpreted diagram image.

    Stubs requirements if none exist yet (see
    ``_stub_requirements_from_diagram``), persists the source file, then
    runs ``design`` through the exact same validate/render/persist pipeline
    ``accept_run``/``refine_architecture`` use
    (``ArchitectureSession.generate_from_design`` — see
    ``app/design/session.py``), so an image-derived architecture is
    indistinguishable, downstream, from a text-derived one. Raises
    ``HTTPException`` (422) if validation/rendering fails, the same as
    those routes. The caller is responsible for ``store.create``/
    ``_upsert_guarded`` afterward — this only touches the in-memory record.
    """

    record.source_filename = filename

    if record.requirements is None:
        if record.requirements_version == 0:
            record.requirements_version = 1
        record.requirements = _stub_requirements_from_diagram(design)
        record.requirements_blob = _persist_requirements_blob(
            image_deps.artifact_store,
            record,
            f"[Uploaded diagram: {filename}]",
            source_filename=filename,
        )

    record.source_file_blob = image_deps.artifact_store.save_source_file(
        record.session_id, record.requirements_version, filename, content
    )

    design_session = ArchitectureSession(
        analyzer=image_deps.design_analyzer,
        diagram_generator=image_deps.diagram_generator,
        validator=image_deps.validator,
        store=image_deps.artifact_store,
        session_id=record.session_id,
        version=record.design_version,
    )

    try:
        result = design_session.generate_from_design(design)
    except DesignGenerationWorkflowError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    record.stage = STAGE_ARCHITECTURE
    record.design_version = result.version
    record.design = result.design
    record.design_blob = result.design_blob
    record.diagram_blob = result.diagram_blob
    # Same "a freshly (re)generated architecture has never been reviewed"
    # reset accept_run/refine_architecture already apply.
    record.approval_status = APPROVAL_PENDING
    record.error = None


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
    dependencies=[Depends(require_role(ROLE_USER))],
)
def start_run(
    body: StartRunRequest,
    request: Request,
    store: Annotated[SessionStore, Depends(get_session_store)],
    artifact_store: Annotated[ArtifactStore, Depends(get_artifact_store)],
    analyzer: Annotated[RequirementsAnalyzer, Depends(get_requirements_analyzer)],
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


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(ROLE_USER))],
)
async def start_run_from_upload(
    request: Request,
    file: Annotated[UploadFile, File()],
    store: Annotated[SessionStore, Depends(get_session_store)],
    deps: Annotated[
        RequirementsUploadDependencies, Depends(get_requirements_upload_dependencies)
    ],
    image_deps: Annotated[
        ImageUploadDependencies, Depends(get_image_upload_dependencies)
    ],
    notes: Annotated[str | None, Form()] = None,
) -> RequirementsRunView:
    """Start a run from an uploaded document, or a diagram image, instead
    of typed text.

    Sibling of ``start_run``: same downstream pipeline (requirements
    analysis, persistence) for a document, just fed extracted text instead
    of a JSON body's ``input`` field. FastAPI can't mix a JSON body with
    multipart ``UploadFile``/``Form`` parsing on one route, hence a
    separate route rather than an optional-file parameter on ``start_run``.

    An uploaded PNG/JPG/JPEG is classified first (``app/vision.py``): a
    document screenshot proceeds through that same requirements pipeline
    (via ``_resolve_image_upload``, then unchanged from here on), while a
    system design/workflow diagram instead jumps this brand-new session
    straight to :data:`STAGE_ARCHITECTURE` — see
    ``_apply_diagram_to_record``.

    ``notes`` is an optional plain-text field the caller can send alongside
    the file — e.g. "focus on the payments section" — appended to the
    extracted document text before analysis (or passed to the diagram
    interpreter as additional context), so a file upload doesn't preclude
    adding a short instruction of its own.
    """
    owner_oid, owner_name = owner_fields(request)
    filename_hint = file.filename or ""

    if is_image_filename(filename_hint):
        filename, content, extracted_text, design = await _resolve_image_upload(
            file,
            deps.extractor,
            image_deps.classifier,
            image_deps.diagram_interpreter,
            notes,
        )
        if design is not None:
            record = SessionRecord(
                session_id=str(uuid.uuid4()),
                owner_oid=owner_oid,
                owner_name=owner_name,
                source_text=f"[Uploaded diagram: {filename}]",
            )
            _apply_diagram_to_record(record, filename, content, design, image_deps)
            store.create(record)
            return RequirementsRunView.from_record(record)
        source_text = f"{extracted_text}\n\n{notes}" if notes else extracted_text
    else:
        extracted_text, content = await _extract_text_from_upload(file, deps.extractor)
        filename = filename_hint or "upload"
        source_text = f"{extracted_text}\n\n{notes}" if notes else extracted_text

    record = SessionRecord(
        session_id=str(uuid.uuid4()),
        owner_oid=owner_oid,
        owner_name=owner_name,
        source_text=source_text,
        source_filename=filename,
    )

    record.requirements_version = 1
    record.requirements = await deps.analyzer.analyze_async(user_input=source_text)
    record.source_file_blob = deps.artifact_store.save_source_file(
        record.session_id, record.requirements_version, filename, content
    )
    record.requirements_blob = _persist_requirements_blob(
        deps.artifact_store, record, source_text, source_filename=filename
    )

    store.create(record)
    return RequirementsRunView.from_record(record)


@router.get(
    "",
    dependencies=[Depends(require_role(*_ANY_ROLE))],
)
def list_runs(
    request: Request,
    store: Annotated[SessionStore, Depends(get_session_store)],
) -> list[RequirementsRunView]:
    """The caller's own sessions, newest first — every session for an Admin.

    With ``AUTH_ENABLED=false`` (or an anonymous, non-Admin caller),
    ``owner_fields`` returns ``(None, None)`` — every session created
    locally is unowned — so this always returns ``[]`` rather than every
    session anyone has ever started. That matches ``SessionStore
    .list_for_owner``'s own "unowned records are nobody's" behavior; it
    isn't a separate special case here. An Admin-role caller instead sees
    every session regardless of owner (``list_all``) — "Admins can manage
    users and access across the system," see ``app/api/ownership.py``'s
    ``is_admin``.
    """
    if is_admin(request):
        records = store.list_all()
        return [RequirementsRunView.from_record(record) for record in records]

    owner_oid, _ = owner_fields(request)
    records = store.list_for_owner(owner_oid) if owner_oid else []
    return [RequirementsRunView.from_record(record) for record in records]


@router.get(
    "/{session_id}",
    dependencies=[Depends(require_role(*_ANY_ROLE))],
)
def get_run(
    session_id: str,
    request: Request,
    store: Annotated[SessionStore, Depends(get_session_store)],
) -> RequirementsRunView:
    record = load_owned(store, session_id, request)
    return RequirementsRunView.from_record(record)


@router.post(
    "/{session_id}/rename",
    dependencies=[Depends(require_role(*_ANY_ROLE))],
)
def rename_run(
    session_id: str,
    body: RenameRunRequest,
    request: Request,
    store: Annotated[SessionStore, Depends(get_session_store)],
) -> RequirementsRunView:
    """Set this session's display name — a label only.

    Open to any of the three functional roles (``Admin`` implicit), not
    gated to a single role the way ``accept``/``approve`` are: renaming
    doesn't advance the session's stage or touch its content, it's metadata
    about a session the caller already owns (or, for ``Admin``, any
    session — see ``load_owned``/``app/api/ownership.py``), the same "any
    functional role can act on what they own" shape as the read routes.
    """
    record = load_owned(store, session_id, request)

    name = body.name.strip()
    if not name:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Name must not be empty."
        )
    if len(name) > MAX_NAME_LENGTH:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Name must be {MAX_NAME_LENGTH} characters or fewer.",
        )

    record.name = name
    _upsert_guarded(store, record)
    return RequirementsRunView.from_record(record)


@router.post(
    "/{session_id}/refine",
    dependencies=[Depends(require_role(ROLE_USER))],
)
def refine_run(
    session_id: str,
    body: RefineRunRequest,
    request: Request,
    store: Annotated[SessionStore, Depends(get_session_store)],
    artifact_store: Annotated[ArtifactStore, Depends(get_artifact_store)],
    analyzer: Annotated[RequirementsAnalyzer, Depends(get_requirements_analyzer)],
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
    # This version came from typed text, not a file — clear any filename
    # left over from a previous version's upload so it isn't misread as
    # describing *this* version's source.
    record.source_filename = None
    record.source_file_blob = None
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
    "/{session_id}/refine/upload",
    dependencies=[Depends(require_role(ROLE_USER))],
)
async def refine_run_from_upload(
    session_id: str,
    request: Request,
    file: Annotated[UploadFile, File()],
    store: Annotated[SessionStore, Depends(get_session_store)],
    deps: Annotated[
        RequirementsUploadDependencies, Depends(get_requirements_upload_dependencies)
    ],
    image_deps: Annotated[
        ImageUploadDependencies, Depends(get_image_upload_dependencies)
    ],
    notes: Annotated[str | None, Form()] = None,
) -> RequirementsRunView:
    """Refine requirements from an uploaded document, or jump straight to
    architecture from an uploaded diagram image, instead of typed text.

    Sibling of ``refine_run`` for the same multipart-vs-JSON-body reason as
    ``start_run_from_upload``. Still only possible while the session is in
    :data:`STAGE_REQUIREMENTS` (same as a text-based refine) — a diagram
    classified here moves the session directly to
    :data:`STAGE_ARCHITECTURE`, the same destination ``accept_run`` reaches
    from typed/OCR'd requirements, just skipping past the intermediate
    requirements-refinement step entirely. See
    ``_apply_diagram_to_record``.
    """
    record = load_owned(store, session_id, request)

    _require_stage(
        record,
        STAGE_REQUIREMENTS,
        f"This session is in stage {record.stage!r}; "
        f"refining is only possible while still in {STAGE_REQUIREMENTS!r}.",
    )

    filename_hint = file.filename or ""

    if is_image_filename(filename_hint):
        filename, content, extracted_text, design = await _resolve_image_upload(
            file,
            deps.extractor,
            image_deps.classifier,
            image_deps.diagram_interpreter,
            notes,
        )
        if design is not None:
            _apply_diagram_to_record(record, filename, content, design, image_deps)
            _upsert_guarded(store, record)
            return RequirementsRunView.from_record(record)
        source_text = f"{extracted_text}\n\n{notes}" if notes else extracted_text
    else:
        extracted_text, content = await _extract_text_from_upload(file, deps.extractor)
        filename = filename_hint or "upload"
        source_text = f"{extracted_text}\n\n{notes}" if notes else extracted_text

    record.requirements_version += 1
    record.source_text = source_text
    record.source_filename = filename
    record.requirements = await deps.analyzer.analyze_async(
        user_input=source_text,
        previous_artifact=record.requirements,
    )
    record.source_file_blob = deps.artifact_store.save_source_file(
        record.session_id, record.requirements_version, filename, content
    )
    record.requirements_blob = _persist_requirements_blob(
        deps.artifact_store, record, source_text, source_filename=filename
    )

    _upsert_guarded(store, record)
    return RequirementsRunView.from_record(record)


@router.post(
    "/{session_id}/accept",
    dependencies=[Depends(require_role(ROLE_ARCHITECT))],
)
def accept_run(
    session_id: str,
    request: Request,
    store: Annotated[SessionStore, Depends(get_session_store)],
    deps: Annotated[
        ArchitectureGenerationDependencies,
        Depends(get_architecture_generation_dependencies),
    ],
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
        analyzer=deps.analyzer,
        diagram_generator=deps.diagram_generator,
        validator=deps.validator,
        store=deps.store,
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
    # A freshly generated architecture has never been reviewed — reset any
    # leftover status from a previous session state (there shouldn't be
    # one, since accept only runs from STAGE_REQUIREMENTS, but this keeps
    # the invariant "approval_status always describes design_version"
    # explicit rather than assumed).
    record.approval_status = APPROVAL_PENDING
    record.error = None

    _upsert_guarded(store, record)
    return RequirementsRunView.from_record(record)


@router.post(
    "/{session_id}/refine-architecture",
    dependencies=[Depends(require_role(ROLE_ARCHITECT))],
)
def refine_architecture(
    session_id: str,
    body: RefineArchitectureRequest,
    request: Request,
    store: Annotated[SessionStore, Depends(get_session_store)],
    deps: Annotated[
        ArchitectureGenerationDependencies,
        Depends(get_architecture_generation_dependencies),
    ],
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
        analyzer=deps.analyzer,
        diagram_generator=deps.diagram_generator,
        validator=deps.validator,
        store=deps.store,
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
    # The design just changed — any prior approve/reject decision was made
    # against the *previous* design_version and must not be read as
    # covering this new one. approval_history is untouched: that decision
    # still happened and stays in the record.
    record.approval_status = APPROVAL_PENDING
    record.error = None

    _upsert_guarded(store, record)
    return RequirementsRunView.from_record(record)


def _record_approval_decision(
    store: SessionStore,
    record: SessionRecord,
    request: Request,
    decision: str,
    reason: str | None,
) -> RequirementsRunView:
    """Shared by ``approve_run``/``reject_run``: both only differ in which
    decision they record, so the stage guard, decision-log append, and
    persistence live in one place rather than being duplicated per route.
    """

    _require_stage(
        record,
        STAGE_ARCHITECTURE,
        f"This session is in stage {record.stage!r}; approving or "
        f"rejecting an architecture is only possible once it's in "
        f"{STAGE_ARCHITECTURE!r}.",
    )
    if record.design is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This session has no architecture to approve or reject yet.",
        )

    _, owner_name = owner_fields(request)

    record.approval_status = decision
    record.approval_history = [
        *record.approval_history,
        ApprovalDecision(
            decision=decision,
            architecture_version=record.design_version,
            reason=reason,
            decided_by=owner_name,
            decided_at=datetime.now(UTC).isoformat(),
        ),
    ]

    _upsert_guarded(store, record)
    return RequirementsRunView.from_record(record)


@router.post(
    "/{session_id}/approve",
    dependencies=[Depends(require_role(ROLE_REVIEWER))],
)
def approve_run(
    session_id: str,
    body: ApprovalDecisionRequest,
    request: Request,
    store: Annotated[SessionStore, Depends(get_session_store)],
) -> RequirementsRunView:
    """Record an "approved" decision against the current architecture version.

    Valid only once a session has reached ``STAGE_ARCHITECTURE``. Can be
    called again later — e.g. to re-approve after a `reject`, or simply to
    record a second reviewer's sign-off — each call appends a new entry to
    ``approval_history`` rather than replacing the previous one.
    """
    record = load_owned(store, session_id, request)
    return _record_approval_decision(
        store, record, request, APPROVAL_APPROVED, body.reason
    )


@router.post(
    "/{session_id}/reject",
    dependencies=[Depends(require_role(ROLE_REVIEWER))],
)
def reject_run(
    session_id: str,
    body: ApprovalDecisionRequest,
    request: Request,
    store: Annotated[SessionStore, Depends(get_session_store)],
) -> RequirementsRunView:
    """Record a "rejected" decision against the current architecture version.

    Unlike a failed `accept`/`refine-architecture`, rejection is a human
    judgment call, not a generation/validation failure — it doesn't touch
    ``stage`` or the persisted design, and doesn't block further
    `refine-architecture` calls. The expected flow is reject → refine →
    re-`approve`, not reject → dead end.
    """
    record = load_owned(store, session_id, request)
    return _record_approval_decision(
        store, record, request, APPROVAL_REJECTED, body.reason
    )


@router.get(
    "/{session_id}/source-file",
    dependencies=[Depends(require_role(*_ANY_ROLE))],
)
def get_source_file(
    session_id: str,
    request: Request,
    store: Annotated[SessionStore, Depends(get_session_store)],
    artifact_store: Annotated[ArtifactStore, Depends(get_artifact_store)],
) -> Response:
    """Download the original uploaded file behind the current requirements version.

    404s if the current requirements version wasn't created from an
    uploaded file (e.g. it came from typed text) — ``record.source_filename``
    is ``None`` in that case, so there's nothing to fetch.
    """
    record = load_owned(store, session_id, request)

    if record.source_filename is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "This requirements version was not created from an uploaded file.",
        )

    found = artifact_store.get_source_file(
        record.session_id, record.requirements_version
    )
    if found is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "The original uploaded file could not be found.",
        )

    content, content_type = found
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": (f'attachment; filename="{record.source_filename}"')
        },
    )
