"""Technical-design entities, mirrored from the orchestrator's
``app.domain.technical_design`` (AI-requirements-to-design-agent's
``backend/orchestrator``).

Deliberate duplication, not an oversight - see ``src/domain/design.py``'s
module docstring for the full rationale (tools-service is an
independently deployable microservice with zero import dependency on the
orchestrator). ``MAX_SECTION_LEVEL`` and the section/table shapes here
must stay in lockstep with the orchestrator's own copy, the same
constraint every other mirrored domain module in this package already
carries.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.domain.design import SystemDesignArtifact
from src.domain.requirements import RequirementsArtifact
from src.domain.work_breakdown import WorkBreakdownArtifact

MAX_SECTION_LEVEL = 3


class DesignTable(BaseModel):
    """A simple, uniform-column table a document section may embed."""

    caption: str = ""
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class DesignSection(BaseModel):
    """One entry in a flat, ordered list of document sections.

    ``level`` (1-``MAX_SECTION_LEVEL``) carries the section's own heading
    depth - see the orchestrator's ``app.domain.technical_design`` module
    docstring for why a flat list with an explicit level, rather than a
    nested tree, was chosen.
    """

    title: str = Field(min_length=1)
    level: int = Field(default=1, ge=1, le=MAX_SECTION_LEVEL)
    body: str = ""
    bullets: list[str] = Field(default_factory=list)
    numbered_steps: list[str] = Field(default_factory=list)
    table: DesignTable | None = None
    include_diagram: bool = False


class TechnicalDesignArtifact(BaseModel):
    """The structured technical design document, as produced by the
    orchestrator's Technical Writer agent."""

    document_title: str = Field(min_length=1)
    system_name: str = ""
    version: str = "1.0"
    executive_summary: str = ""
    sections: list[DesignSection] = Field(default_factory=list)


class TechnicalDesignExport(BaseModel):
    """The rendered ``.docx`` (as base64 text - see this project's MCP
    envelope, which is JSON and has no binary type) plus a summary of
    what was rendered."""

    docx_base64: str
    filename: str = ""
    heading_count: int = 0
    table_count: int = 0
    diagram_embedded: bool = False
    byte_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class TechnicalDesignExportRequest(BaseModel):
    """Export request: the document plus the upstream artifacts its
    embedded diagram and traceability appendix are rendered from.

    Same "take the full upstream artifacts, not pre-extracted fields"
    shape as ``src.domain.work_breakdown.WorkBreakdownExportRequest`` -
    keeps the actual rendering rules in
    ``src.infrastructure.document_export`` alone.
    """

    document: TechnicalDesignArtifact
    design: SystemDesignArtifact
    requirements: RequirementsArtifact
    work_breakdown: WorkBreakdownArtifact
