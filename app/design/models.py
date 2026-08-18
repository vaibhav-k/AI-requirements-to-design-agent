from __future__ import annotations

from pydantic import BaseModel, Field


class DesignComponent(BaseModel):
    """A logical component in the high-level architecture."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    responsibility: str = Field(min_length=1)

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
    ``app/infrastructure/session_store.py``) — an append-only log, never
    rewritten or removed, so a session's full approval history survives
    every later refinement rather than only reflecting the latest decision.
    """

    decision: str = Field(min_length=1)  # "approved" | "rejected"
    architecture_version: int
    reason: str | None = None
    decided_by: str | None = None
    decided_at: str
