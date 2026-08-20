"""The requirements-to-architecture run bounded context's entity.

``SessionRecord`` moved here, verbatim, from
``app/infrastructure/session_store.py`` as part of "Ports + adapters for
storage" (see README -> "Clean Architecture Migration") — the same "pure
entity, zero I/O" home ``app.domain.requirements``/``app.domain.design``
already give their own bounded contexts' entities.

One honest compromise, called out rather than hidden: ``etag`` is an
optimistic-concurrency token, not a business concept a domain entity
would otherwise need to know about. It stays here anyway rather than
splitting it into a separate infrastructure-only wrapper type, because
every layer above the store (``app/api/routes/requirements.py``'s
``_upsert_guarded``, ``app/api/ownership.py``) already reads/threads it
through as plain data — "the record I read back has a concurrency token
I hand back on write" is a genuinely cross-cutting idea a fair number of
storage backends share (Cosmos ETags, S3 version IDs, a bare row
version column), not something unique to
``app.infrastructure.session_store.CosmosSessionStore``. Splitting it out
would mean either every route also imports an infrastructure-only type
just to pass it through unread, or ``SessionStorePort`` doing the
threading itself — neither reads as clearer than accepting this one
field as domain-adjacent plumbing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.design import ApprovalDecision, SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


class SessionRecord(BaseModel):
    """One requirements-to-design run. Persisted as a Cosmos document (id=session_id).

    Mirrors the CLI's own versioning model: ``requirements_version`` bumps on
    every analyze/refine (``DesignSession.version``). ``design_version`` bumps
    the same way once an architecture exists: once on accept, and again on
    every subsequent ``refine-architecture`` call (``ArchitectureSession.version``)
    — the architecture analogue of requirements refinement. ``approval_status``/
    ``approval_history`` track whether the *current* design version has been
    signed off on — see ``app/api/routes/requirements.py``'s
    ``approve_run``/``reject_run``.
    """

    model_config = ConfigDict(populate_by_name=True)

    session_id: str
    owner_oid: str | None = None
    owner_name: str | None = None

    name: str | None = None
    """User-editable display label for this session (e.g. "Checkout revamp"),
    distinct from ``session_id`` and from ``owner_name``. ``None`` until
    someone renames it (``PATCH /requirements-runs/{id}/name``), in which
    case the UI falls back to showing a shortened ``session_id``. Purely a
    label — never read by any analyzer or generation step, and renaming
    doesn't bump any version counter.
    """

    stage: str = "requirements"  # "requirements" | "generating" | "architecture"

    source_text: str = ""
    source_filename: str | None = None
    """Original uploaded filename for the *current* requirements version,
    if it came from a file upload rather than typed text (see
    ``app/ingestion.py`` and the ``/upload`` routes in
    ``app/api/routes/requirements.py``). Reset to ``None`` whenever a
    version is created from typed text instead.
    """
    source_file_blob: str | None = None
    """Blob name of the persisted original file for ``source_filename``,
    written via ``ArtifactStorePort.save_source_file``. ``None`` whenever
    ``source_filename`` is ``None``.
    """
    requirements_version: int = 0
    requirements: RequirementsArtifact | None = None
    requirements_blob: str | None = None

    design_version: int = 0
    design: SystemDesignArtifact | None = None
    design_blob: str | None = None
    diagram_blob: str | None = None

    # "pending" | "approved" | "rejected". Only meaningful once `stage` is
    # `"architecture"` — reset to "pending" every time `design_version`
    # changes (on `accept` and on every `refine-architecture`), since an
    # approval decision made against one design version should never be
    # read as covering a *different*, later version of that design. See
    # `app/api/routes/requirements.py`'s `approve_run`/`reject_run`.
    approval_status: str = "pending"
    # Append-only — every decision ever made against this session, oldest
    # first, even ones superseded by a later refinement + re-approval.
    # `approval_status` alone answers "what's the current decision";
    # `approval_history` answers "what decisions were ever made, by whom,
    # against which version, and why."
    approval_history: list[ApprovalDecision] = Field(default_factory=list)

    error: str | None = None

    created_at: str = Field(default_factory=utcnow_iso)
    updated_at: str = Field(default_factory=utcnow_iso)

    # Cosmos's own concurrency token (its ``_etag`` system property), carried
    # on the model so a later ``upsert()`` can pass it back as an if-match
    # condition — see ``CosmosSessionStore.upsert``. Populated automatically
    # when a record is read back from Cosmos (``get``/``list_for_owner``);
    # ``None`` on a record that was only ever constructed in Python and never
    # round-tripped, in which case ``upsert`` falls back to an unconditional
    # write. Never sent as part of the document body (``exclude=True``) —
    # Cosmos manages ``_etag`` itself, so this is read-only, not writable.
    etag: str | None = Field(default=None, alias="_etag", exclude=True)

    def to_item(self) -> dict[str, Any]:
        item = self.model_dump(mode="json")
        item["id"] = self.session_id
        return item
