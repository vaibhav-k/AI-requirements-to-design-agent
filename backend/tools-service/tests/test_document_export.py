"""Unit tests for ``src.infrastructure.document_export.TechnicalDesignExporter``.

Complements ``tests/test_routes.py``'s route-level smoke tests with
direct exercise of the exporter's own logic: structural validation, the
traceability/work-breakdown appendices, and the "no diagram to embed"
degrade-gracefully path.
"""

from __future__ import annotations

import io

from docx import Document
from docx.document import Document as DocxDocument

from src.domain.design import DesignComponent, SystemDesignArtifact
from src.domain.errors import TechnicalDesignExportError
from src.domain.requirements import Requirement, RequirementsArtifact
from src.domain.technical_design import (
    DesignSection,
    DesignTable,
    TechnicalDesignArtifact,
    TechnicalDesignExportRequest,
)
from src.domain.work_breakdown import (
    WorkBreakdownArtifact,
    WorkBreakdownFeature,
    WorkBreakdownStory,
    WorkBreakdownTask,
)
from src.infrastructure.document_export import TechnicalDesignExporter

_REQUIREMENTS = RequirementsArtifact(
    summary="A minimal system.",
    business_goal="Manage customers.",
    actors=[],
    functional_requirements=[
        Requirement(id="FR-001", description="Handle requests.", priority="high")
    ],
    non_functional_requirements=[],
    data_requirements=[],
    integration_requirements=[],
    constraints=[],
    assumptions=[],
    open_questions=[],
)

_WORK_BREAKDOWN = WorkBreakdownArtifact(
    features=[
        WorkBreakdownFeature(
            feature="Customer Management",
            stories=[
                WorkBreakdownStory(
                    story="Create customer",
                    tasks=[
                        WorkBreakdownTask(
                            task="Implement POST /customers endpoint",
                            description="Add the endpoint.",
                            effort="M",
                            requirement_ids=["FR-001"],
                            architecture_ids=["api"],
                        )
                    ],
                )
            ],
        )
    ],
    ambiguities=[],
)


def _design_with_component() -> SystemDesignArtifact:
    return SystemDesignArtifact(
        architecture_summary="A minimal architecture.",
        components=[
            DesignComponent(id="api", name="API", responsibility="Handles requests.")
        ],
    )


def _open_docx(docx_base64: str) -> DocxDocument:
    import base64

    return Document(io.BytesIO(base64.b64decode(docx_base64)))


def test_export_renders_sections_and_traceability_appendix() -> None:
    document = TechnicalDesignArtifact(
        document_title="Customer Management Technical Design",
        system_name="Customer Management System",
        executive_summary="A minimal system for managing customers.",
        sections=[
            DesignSection(
                title="Architecture Overview",
                level=1,
                body="The system exposes a single API component.",
                include_diagram=True,
            ),
            DesignSection(
                title="Data Model",
                level=2,
                body="",
                table=DesignTable(
                    headers=["Field", "Type"],
                    rows=[["id", "string"], ["name", "string"]],
                ),
            ),
        ],
    )

    request = TechnicalDesignExportRequest(
        document=document,
        design=_design_with_component(),
        requirements=_REQUIREMENTS,
        work_breakdown=_WORK_BREAKDOWN,
    )

    export = TechnicalDesignExporter().export(request)

    assert export.byte_count > 0
    assert export.diagram_embedded is True
    assert export.table_count >= 2  # the section's own table + the appendix table
    assert export.filename == "technical-design.docx"

    docx = _open_docx(export.docx_base64)
    full_text = "\n".join(paragraph.text for paragraph in docx.paragraphs)
    assert "Customer Management Technical Design" in full_text
    assert "Architecture Overview" in full_text
    assert "Appendix A - Requirements Traceability" in full_text
    assert "Appendix B - Implementation Work Summary" in full_text


def test_export_rejects_document_with_no_sections() -> None:
    document = TechnicalDesignArtifact(
        document_title="Empty Document",
        sections=[],
    )
    request = TechnicalDesignExportRequest(
        document=document,
        design=_design_with_component(),
        requirements=_REQUIREMENTS,
        work_breakdown=_WORK_BREAKDOWN,
    )

    try:
        TechnicalDesignExporter().export(request)
        raised = False
    except TechnicalDesignExportError:
        raised = True

    assert raised


def test_export_without_components_has_no_diagram_and_no_warning() -> None:
    """A design with no components has nothing to diagram - this should
    not be treated as a failed embed (no warning), just nothing to embed."""

    document = TechnicalDesignArtifact(
        document_title="No-Component Document",
        sections=[
            DesignSection(title="Overview", level=1, body="Nothing to diagram yet.")
        ],
    )
    request = TechnicalDesignExportRequest(
        document=document,
        design=SystemDesignArtifact(architecture_summary="Empty.", components=[]),
        requirements=_REQUIREMENTS,
        work_breakdown=_WORK_BREAKDOWN,
    )

    export = TechnicalDesignExporter().export(request)

    assert export.diagram_embedded is False
    assert export.warnings == []
