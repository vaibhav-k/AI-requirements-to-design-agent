"""Requirements bounded context - domain entities and value objects.

Moved verbatim from ``app/models.py`` as the first slice of the Clean
Architecture migration (see README). ``app/models.py`` used to
re-export everything from this module for backward compatibility while
the rest of the codebase (storage, API routes, MCP server, CLI, tests)
still imported from the old path; it has since been deleted once every
importer migrated to ``app.domain.requirements`` directly (see README ->
"Clean Architecture Migration").

Nothing in this module performs I/O or imports anything from
``app.application``, ``app.infrastructure``, ``app.api``, ``app.web``,
or ``app.mcp`` - see ``app/domain/__init__.py`` for why.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Requirement(BaseModel):
    """A functional or non-functional requirement."""

    id: str
    description: str
    priority: str = Field(description="Priority: high, medium, or low")
    rationale: str | None = None


class Actor(BaseModel):
    """A user, system, or other actor involved in the requirements."""

    name: str
    description: str


class Assumption(BaseModel):
    """An assumption made while interpreting the requirements."""

    id: str
    assumption: str
    reason: str
    confidence: str = Field(description="Confidence: high, medium, or low")


class OpenQuestion(BaseModel):
    """An unresolved question about the requirements."""

    id: str
    question: str
    reason: str
    blocking: bool = False


class RequirementsArtifact(BaseModel):
    """Structured representation of the user's requirements."""

    summary: str
    business_goal: str

    actors: list[Actor]
    functional_requirements: list[Requirement]
    non_functional_requirements: list[Requirement]

    data_requirements: list[str]
    integration_requirements: list[str]
    constraints: list[str]

    assumptions: list[Assumption]
    open_questions: list[OpenQuestion]


class StoredArtifact(BaseModel):
    """Versioned artifact persisted in Azure Blob Storage."""

    artifact_id: str
    session_id: str
    artifact_type: str
    version: int
    created_at: str
    source_text: str
    requirements: RequirementsArtifact
    source_filename: str | None = None
    """Original uploaded filename, if this artifact came from a file upload.

    ``None`` for typed-text input (see ``app/ingestion.py``). When set, the
    original file bytes are persisted separately via
    ``ArtifactStore.save_source_file`` - this field is just the pointer
    back to "was there a file, and what was it called."
    """
