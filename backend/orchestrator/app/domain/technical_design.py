"""The technical-design-document bounded context's entities.

Fourth and final pipeline stage, one step after the work breakdown (see
``app.domain.work_breakdown``): turns the approved requirements,
architecture, and work breakdown into a structured technical design
document - the content a reviewer reads section by section, and that
``backend/tools-service`` deterministically renders to a Word (.docx)
file for download (see that service's ``src/domain/technical_design.py``
and ``src/infrastructure/document_export.py``).

Modeled on Parnell-AI-Persona-Agent's own design-document contract
(``backend/orchestrator/src/domain/contracts/technical_design.py``
there) - a flat, ordered list of sections carrying their own heading
``level`` rather than a nested tree, since nested Pydantic models make
structured LLM output unreliable and a flat list still renders, numbers,
and validates cleanly (outline numbers like "2.1" are derived from the
level sequence by the renderer, not stored here). Unlike Parnell, this
module has no human-in-the-loop gate contracts of its own
(``DesignDocApprovalRequest``/``Response`` there) - this project's
Approve/Refine loop is the same generic ``approval_status``/
``approval_history`` pair on ``app.domain.session.SessionRecord`` every
other stage already uses, not a per-stage contract.

Nothing in this module performs I/O - see ``app/domain/__init__.py``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MAX_SECTION_LEVEL = 3
"""Deepest heading level a section may declare - "1.2.3" is as deep as
the rendered outline numbering goes. Matches
``backend/tools-service/src/infrastructure/document_export.py``'s
``MAX_LEVEL``, which clamps to the same bound independently (tools-service
has no import dependency on this module - see
``src/domain/design.py``'s docstring there for why that duplication is
deliberate)."""

SectionKind = Literal["prose", "bullets", "numbered_steps", "table"]
"""Which of ``DesignSection``'s content fields actually holds this
section's body. Recorded explicitly rather than left for the renderer to
infer from which fields are non-empty, since a section can legitimately
have prose *and* a table (e.g. a paragraph introducing the table that
follows it) - ``kind`` says which one is the section's primary content
for numbering/rendering purposes."""


class DesignTable(BaseModel):
    """Tabular content inside a section - used for whatever the section
    needs (a comparison, a schema, a decision matrix), not a fixed shape."""

    caption: str = Field(default="", description="Short caption shown under the table.")
    headers: list[str] = Field(default_factory=list, description="Column headers.")
    rows: list[list[str]] = Field(
        default_factory=list,
        description="Rows of cells. Every row must have exactly as many "
        "cells as there are headers.",
    )


class DesignSection(BaseModel):
    """One section of the document, in reading order.

    Sections are a flat ordered list carrying depth in ``level`` rather
    than a nested tree - see this module's docstring for why. Order
    matters: outline numbers are derived from the ``level`` sequence by
    ``backend/tools-service``'s renderer, not stored on the section itself.
    """

    title: str = Field(min_length=1, description="Section heading.")
    level: int = Field(
        default=1,
        ge=1,
        le=MAX_SECTION_LEVEL,
        description=f"Heading depth, 1-{MAX_SECTION_LEVEL}. A level-2 "
        "section belongs to the nearest preceding level-1 section. Never "
        "skip a level.",
    )
    body: str = Field(
        default="",
        description="The section's prose: 1-3 short paragraphs, "
        "separated by newlines. Real content, never a placeholder.",
    )
    bullets: list[str] = Field(
        default_factory=list,
        description="Bullet points, when a list reads better than prose.",
    )
    numbered_steps: list[str] = Field(
        default_factory=list,
        description="Ordered steps, for sequences such as a request workflow.",
    )
    table: DesignTable | None = Field(
        default=None, description="A table, when the content is genuinely tabular."
    )
    include_diagram: bool = Field(
        default=False,
        description="Set on exactly one section - the approved "
        "architecture diagram is embedded there.",
    )


class TechnicalDesignArtifact(BaseModel):
    """The structured technical design document - the pre-render shape a
    ``TechnicalWriterAgentPort`` implementation produces, and a
    refinement round trips through.

    Rendered to an actual ``.docx`` file (Table of Contents, numbered
    headings, the embedded architecture diagram, appendices) by
    ``backend/tools-service`` - see ``app.application.ports
    .DocumentExporterPort``. This artifact is the document's content, not
    the rendered file.
    """

    document_title: str = Field(
        min_length=1,
        description="Document title, e.g. "
        "'<System> - Solution Architecture & Technical Design'.",
    )
    system_name: str = Field(default="", description="The system this design is for.")
    version: str = Field(default="1.0", description="Document version label.")
    executive_summary: str = Field(
        default="",
        description="2-4 sentences a stakeholder can read on its own: "
        "what is being built and how it will be delivered.",
    )
    sections: list[DesignSection] = Field(
        default_factory=list,
        description="The document body, in reading order.",
    )


class TechnicalDesignExport(BaseModel):
    """The rendered ``.docx`` plus the render summary produced alongside
    it.

    Produced by ``backend/tools-service`` (see that service's
    ``src/infrastructure/document_export.py``) from a
    ``TechnicalDesignArtifact`` plus the approved architecture diagram and
    work breakdown it was compiled from - the technical-design analogue
    of ``app.domain.work_breakdown.WorkBreakdownExport``.
    """

    docx_base64: str = Field(description="Base64-encoded .docx file bytes.")
    filename: str = Field(default="", description="Suggested download filename.")
    heading_count: int = 0
    table_count: int = 0
    diagram_embedded: bool = False
    byte_count: int = 0
    warnings: list[str] = Field(
        default_factory=list,
        description="Structural problems found while rendering (e.g. the "
        "architecture diagram could not be embedded).",
    )
