"""The architecture/design bounded context's entities.

Moved here, verbatim, from the former ``app/design/models.py`` as part
of the Clean Architecture migration (see README -> "Clean Architecture
Migration") - the same "pure entity, zero I/O" home
``app.domain.requirements`` already gives the requirements bounded
context's entities. Nothing here depends on Pydantic beyond what every
other domain module already accepts as a shared-kernel dependency (see
``app/domain/__init__.py``).

``app/design/models.py`` used to be a deprecated re-export shim over
this module, the same "strangler fig" shape ``app/models.py`` used for
``app.domain.requirements`` - it has since been deleted (see README ->
"Clean Architecture Migration" -> the slice that migrated every
remaining importer off both shims). Every module that used to import
``SystemDesignArtifact`` and friends from ``app.design.models``
(``app/design/analyzer.py``, ``app/design/validator.py``,
``app/design/diagram.py``, ``app/design/comparison.py``,
``app/design/session.py``, the API routes, the MCP server,
``app/main.py``, ``app/infrastructure/session_store.py``,
``app/vision.py``, and all of ``tests/``) now imports directly from
here.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DesignComponent(BaseModel):
    """A logical component in the high-level architecture."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    responsibility: str = Field(min_length=1)

    # A short group/category name (e.g. "Client & Identity", "Data
    # Platform") shared by every component that logically belongs
    # together. Optional and blank by default so existing designs (and
    # any code constructing a `DesignComponent` without it) keep working
    # unchanged; `ArchitectureDiagramGenerator` treats a blank domain as
    # its own single "Other Components" group rather than requiring one.
    # See `app/design/diagram.py` for how this drives per-domain
    # clustering in the rendered diagram.
    domain: str = Field(default="")

    requirement_ids: list[str] = Field(default_factory=list)


class DesignInterface(BaseModel):
    """A logical interaction between two architecture components."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)

    source_component: str = Field(min_length=1)
    target_component: str = Field(min_length=1)

    requirement_ids: list[str] = Field(default_factory=list)


class ExternalDependency(BaseModel):
    """An external service or dependency used by the system."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)

    used_by_components: list[str] = Field(default_factory=list)


class DesignAssumption(BaseModel):
    """An assumption made while creating the architecture."""

    id: str = Field(min_length=1)
    assumption: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class DesignQuestion(BaseModel):
    """An architecture question that remains unresolved."""

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class SystemDesignArtifact(BaseModel):
    """High-level system architecture generated from requirements."""

    architecture_summary: str = Field(min_length=1)

    components: list[DesignComponent] = Field(default_factory=list)

    interfaces: list[DesignInterface] = Field(default_factory=list)

    external_dependencies: list[ExternalDependency] = Field(default_factory=list)

    assumptions: list[DesignAssumption] = Field(default_factory=list)

    open_questions: list[DesignQuestion] = Field(default_factory=list)


class ApprovalDecision(BaseModel):
    """One approve/reject decision recorded against an architecture version.

    Persisted on ``SessionRecord.approval_history`` (see
    ``app/infrastructure/session_store.py``) - an append-only log, never
    rewritten or removed, so a session's full approval history survives
    every later refinement rather than only reflecting the latest decision.
    """

    decision: str = Field(min_length=1)  # "approved" | "rejected"
    architecture_version: int
    reason: str | None = None
    decided_by: str | None = None
    decided_at: str
