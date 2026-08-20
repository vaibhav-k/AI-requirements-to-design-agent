"""The work-breakdown bounded context's entities.

Third pipeline stage after requirements analysis and system design (see
``app.domain.requirements``/``app.domain.design``): turns an approved
``RequirementsArtifact`` + ``SystemDesignArtifact`` pair into an
implementation-ready Feature -> Story -> Task hierarchy with per-item
traceability back to the requirement/architecture IDs that justify it.

Modeled directly on the Work Breakdown Agent specification this project
was given (hierarchy, effort scale, exact CSV column order, "never
fabricate an ID" rule) rather than on
Parnell-AI-Persona-Agent's own task-planning contract
(``backend/orchestrator/src/domain/contracts/task_plan.py`` there) - that
project's ``WorkItem`` carries story points, WBS codes, sprints, and
phases that nothing in this project's specification asked for. What *is*
taken from Parnell is the shape of the split itself: a structured
artifact produced by an LLM-backed agent here, handed to a deterministic,
LLM-free exporter/validator that lives in ``backend/tools-service`` (see
that service's own ``src/domain/work_breakdown.py`` and
``src/infrastructure/work_breakdown_export.py``) - the same
agent-produces/tools-service-validates split
``DiagramRendererPort``/``ArchitectureValidatorPort`` already use for
diagrams and architecture validation.

Nothing in this module performs I/O - see ``app/domain/__init__.py``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EffortEstimate = Literal["XS", "S", "M", "L", "XL"]
"""Implementation-effort scale a Task is estimated on.

XS < 0.5 day, S = 0.5-1 day, M = 1-3 days, L = 3-5 days, XL > 5 days.
Represents implementation effort, not calendar duration - see
``EFFORT_LEGEND`` for the human-readable text of each value.
"""

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
    """A concrete, independently-assignable implementation activity.

    Traces back to the requirement(s) and/or architecture element(s) that
    drove it - every task must carry at least one of ``requirement_ids``/
    ``architecture_ids``, never neither (see the Work Breakdown Agent
    rule "every work item must have traceability to at least one valid
    Requirement ID and/or Architecture ID").
    """

    task: str = Field(min_length=1, description="Specific, actionable task name.")
    description: str = Field(
        min_length=1,
        description="What needs to be done and the expected outcome.",
    )
    effort: EffortEstimate
    requirement_ids: list[str] = Field(default_factory=list)
    architecture_ids: list[str] = Field(default_factory=list)


class WorkBreakdownStory(BaseModel):
    """A meaningful user, business, or technical outcome within a Feature."""

    story: str = Field(min_length=1, description="Story name.")
    tasks: list[WorkBreakdownTask] = Field(default_factory=list)


class WorkBreakdownFeature(BaseModel):
    """A major capability or logical area of the solution."""

    feature: str = Field(min_length=1, description="Feature name.")
    stories: list[WorkBreakdownStory] = Field(default_factory=list)


class WorkBreakdownAmbiguity(BaseModel):
    """A gap or conflict flagged instead of silently invented or resolved.

    Covers every "flag rather than invent" rule in the specification: a
    requirement with no architecture mapping, an architecture element
    with no requirement mapping, a requirement or architecture element
    that needs implementation but has no corresponding work item, and any
    outright conflict between the requirements and the architecture.
    """

    kind: AmbiguityKind
    description: str = Field(min_length=1)
    related_ids: list[str] = Field(default_factory=list)


class WorkBreakdownArtifact(BaseModel):
    """The structured Feature -> Story -> Task work breakdown.

    Rendered to the RFC-compliant CSV the specification requires
    (``feature,story,task,description,effort,requirement_ids,
    architecture_ids``) by ``backend/tools-service``'s deterministic
    exporter - this artifact itself is the pre-CSV structured shape an
    ``AgentFrameworkWorkBreakdownAgent`` produces and a refinement round
    trips through, not the CSV text itself.
    """

    features: list[WorkBreakdownFeature] = Field(default_factory=list)
    ambiguities: list[WorkBreakdownAmbiguity] = Field(default_factory=list)


class WorkBreakdownExport(BaseModel):
    """The rendered CSV plus the validation summary the specification
    requires alongside it.

    Produced by ``backend/tools-service`` (see that service's
    ``src/infrastructure/work_breakdown_export.py``) from a
    ``WorkBreakdownArtifact`` plus the requirement/architecture IDs the
    upstream ``RequirementsArtifact``/``SystemDesignArtifact`` actually
    declare - the only place either ID set is known well enough to catch
    a fabricated ID or an uncovered requirement/architecture element.
    """

    csv_text: str = Field(
        description="The complete RFC-compliant CSV document, header row included."
    )
    feature_count: int = 0
    story_count: int = 0
    task_count: int = 0
    covered_requirement_ids: list[str] = Field(default_factory=list)
    covered_architecture_ids: list[str] = Field(default_factory=list)
    unmapped_requirement_ids: list[str] = Field(
        default_factory=list,
        description="Requirement IDs from the input that no work item references.",
    )
    unmapped_architecture_ids: list[str] = Field(
        default_factory=list,
        description="Architecture IDs from the input that no work item references.",
    )
    fabricated_requirement_ids: list[str] = Field(
        default_factory=list,
        description="Requirement IDs referenced by a work item that do not exist "
        "in the supplied RequirementsArtifact - should always be empty; a "
        "non-empty list means the agent violated the 'never fabricate an ID' rule.",
    )
    fabricated_architecture_ids: list[str] = Field(
        default_factory=list,
        description="Architecture IDs referenced by a work item that do not exist "
        "in the supplied SystemDesignArtifact - should always be empty, for the "
        "same reason as fabricated_requirement_ids.",
    )
    ambiguities: list[WorkBreakdownAmbiguity] = Field(default_factory=list)
    warnings: list[str] = Field(
        default_factory=list,
        description="Structural problems found while validating the breakdown "
        "(e.g. a task with no traceability at all).",
    )
