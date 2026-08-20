"""Requirements-artifact entities, mirrored from the orchestrator's
``app.domain.requirements`` (AI-requirements-to-design-agent's
``backend/orchestrator``).

Deliberate duplication, not an oversight - see ``src/domain/design.py``'s
module docstring for the full rationale. Only what
``work_breakdown_export.py`` actually needs is reproduced here -
``StoredArtifact`` (Blob-storage persistence, not a work-breakdown
concern) stays orchestrator-only.
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
