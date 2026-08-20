"""Work-breakdown entities, mirrored from the orchestrator's
``app.domain.work_breakdown`` (AI-requirements-to-design-agent's
``backend/orchestrator``).

Deliberate duplication, not an oversight - see ``src/domain/design.py``'s
module docstring for the full rationale (tools-service is an
independently deployable microservice with zero import dependency on the
orchestrator).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.domain.design import SystemDesignArtifact
from src.domain.requirements import RequirementsArtifact

EffortEstimate = Literal["XS", "S", "M", "L", "XL"]

EFFORT_LEGEND: dict[EffortEstimate, str] = {
    "XS": "Less than 0.5 day",
    "S": "0.5-1 day",
    "M": "1-3 days",
    "L": "3-5 days",
    "XL": "More than 5 days",
}

AmbiguityKind = Literal[
    "requirement_without_architecture",
    "architecture_without_requirement",
    "requirement_without_work_item",
    "architecture_without_work_item",
    "conflicting_inputs",
    "assumption",
]


class WorkBreakdownTask(BaseModel):
    """A concrete, independently-assignable implementation activity."""

    task: str = Field(min_length=1)
    description: str = Field(min_length=1)
    effort: EffortEstimate
    requirement_ids: list[str] = Field(default_factory=list)
    architecture_ids: list[str] = Field(default_factory=list)


class WorkBreakdownStory(BaseModel):
    """A meaningful user, business, or technical outcome within a Feature."""

    story: str = Field(min_length=1)
    tasks: list[WorkBreakdownTask] = Field(default_factory=list)


class WorkBreakdownFeature(BaseModel):
    """A major capability or logical area of the solution."""

    feature: str = Field(min_length=1)
    stories: list[WorkBreakdownStory] = Field(default_factory=list)


class WorkBreakdownAmbiguity(BaseModel):
    """A gap or conflict flagged instead of silently invented or resolved."""

    kind: AmbiguityKind
    description: str = Field(min_length=1)
    related_ids: list[str] = Field(default_factory=list)


class WorkBreakdownArtifact(BaseModel):
    """The structured Feature -> Story -> Task work breakdown, as produced
    by the orchestrator's Work Breakdown Agent."""

    features: list[WorkBreakdownFeature] = Field(default_factory=list)
    ambiguities: list[WorkBreakdownAmbiguity] = Field(default_factory=list)


class WorkBreakdownExport(BaseModel):
    """The rendered CSV plus the validation summary this tool produces."""

    csv_text: str = Field(
        description="The complete RFC-compliant CSV document, header row included."
    )
    feature_count: int = 0
    story_count: int = 0
    task_count: int = 0
    covered_requirement_ids: list[str] = Field(default_factory=list)
    covered_architecture_ids: list[str] = Field(default_factory=list)
    unmapped_requirement_ids: list[str] = Field(default_factory=list)
    unmapped_architecture_ids: list[str] = Field(default_factory=list)
    fabricated_requirement_ids: list[str] = Field(default_factory=list)
    fabricated_architecture_ids: list[str] = Field(default_factory=list)
    ambiguities: list[WorkBreakdownAmbiguity] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WorkBreakdownExportRequest(BaseModel):
    """Export/validate request: the breakdown plus the upstream artifacts
    to validate its traceability against.

    Takes the full ``RequirementsArtifact``/``SystemDesignArtifact``
    (mirrored in ``src.domain.requirements``/``src.domain.design``)
    rather than pre-extracted ID lists, so the definition of "a valid
    requirement/architecture ID" lives in exactly one place -
    ``src.infrastructure.work_breakdown_export`` - the same "keep the
    business rule in tools-service, keep the wrapper a dumb pass-through"
    split ``validate``/``generate`` already use.
    """

    breakdown: WorkBreakdownArtifact
    requirements: RequirementsArtifact
    design: SystemDesignArtifact
