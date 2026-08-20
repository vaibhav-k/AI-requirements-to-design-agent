"""Design-artifact entities, mirrored from the orchestrator's
``app.domain.design`` (AI-requirements-to-design-agent's ``backend/orchestrator``).

This is a deliberate, intentional duplication, not an oversight: tools-service
is an independently deployable microservice (own ``requirements.txt``, own
Dockerfile, own process) with zero import dependency on the orchestrator's
codebase - the same pattern Parnell-AI-Persona-Agent's ``backend/tools-service``
uses for its own ``domain/tools/*/models.py``. Keeping these Pydantic models
byte-for-byte identical to the orchestrator's is a *process* concern (review
both when the shared shape changes), not something a shared package solves
for free - Parnell doesn't share one either, for the same reason: it would
re-couple two services whose whole point is independent deployability.

Only the subset ``diagram.py``/``validator.py`` actually need is reproduced
here - ``ApprovalDecision`` (session/workflow state, not a rendering or
validation concern) stays orchestrator-only.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DesignComponent(BaseModel):
    """A logical component in the high-level architecture."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    responsibility: str = Field(min_length=1)

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
