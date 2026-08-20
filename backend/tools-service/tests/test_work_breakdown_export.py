from __future__ import annotations

import csv
import io

import pytest

from src.domain.design import DesignComponent, SystemDesignArtifact
from src.domain.errors import WorkBreakdownExportError
from src.domain.requirements import Requirement, RequirementsArtifact
from src.domain.work_breakdown import (
    WorkBreakdownAmbiguity,
    WorkBreakdownArtifact,
    WorkBreakdownExportRequest,
    WorkBreakdownFeature,
    WorkBreakdownStory,
    WorkBreakdownTask,
)
from src.infrastructure.work_breakdown_export import (
    CSV_COLUMNS,
    WorkBreakdownExporter,
)


def _requirements(*ids: str) -> RequirementsArtifact:
    return RequirementsArtifact(
        summary="s",
        business_goal="g",
        actors=[],
        functional_requirements=[
            Requirement(id=i, description=f"Requirement {i}.", priority="high")
            for i in ids
        ],
        non_functional_requirements=[],
        data_requirements=[],
        integration_requirements=[],
        constraints=[],
        assumptions=[],
        open_questions=[],
    )


def _design(*ids: str) -> SystemDesignArtifact:
    return SystemDesignArtifact(
        architecture_summary="A design.",
        components=[
            DesignComponent(id=i, name=i, responsibility=f"Does {i}.") for i in ids
        ],
    )


def _task(
    task: str = "Implement POST /customers endpoint",
    requirement_ids: list[str] | None = None,
    architecture_ids: list[str] | None = None,
) -> WorkBreakdownTask:
    return WorkBreakdownTask(
        task=task,
        description="Add the endpoint and validation.",
        effort="M",
        requirement_ids=requirement_ids if requirement_ids is not None else ["FR-001"],
        architecture_ids=architecture_ids if architecture_ids is not None else ["api"],
    )


def _breakdown(*tasks: WorkBreakdownTask) -> WorkBreakdownArtifact:
    return WorkBreakdownArtifact(
        features=[
            WorkBreakdownFeature(
                feature="Customer Management",
                stories=[
                    WorkBreakdownStory(story="Create customer", tasks=list(tasks))
                ],
            )
        ]
    )


def _parse_csv(csv_text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(csv_text)))


def test_export_renders_the_exact_column_order() -> None:
    request = WorkBreakdownExportRequest(
        breakdown=_breakdown(_task()),
        requirements=_requirements("FR-001"),
        design=_design("api"),
    )

    export = WorkBreakdownExporter().export(request)

    header = export.csv_text.splitlines()[0]
    assert header == ",".join(CSV_COLUMNS)


def test_export_produces_one_row_per_task_with_comma_joined_ids() -> None:
    request = WorkBreakdownExportRequest(
        breakdown=_breakdown(
            _task(requirement_ids=["FR-001", "NFR-001"], architecture_ids=["api"])
        ),
        requirements=_requirements("FR-001", "NFR-001"),
        design=_design("api"),
    )

    export = WorkBreakdownExporter().export(request)
    rows = _parse_csv(export.csv_text)

    assert len(rows) == 1
    assert rows[0]["feature"] == "Customer Management"
    assert rows[0]["story"] == "Create customer"
    assert rows[0]["requirement_ids"] == "FR-001,NFR-001"
    assert rows[0]["architecture_ids"] == "api"


def test_export_rfc_compliant_escaping_for_commas_and_quotes() -> None:
    task = _task(
        task='Add "quoted" task, with a comma',
    )
    request = WorkBreakdownExportRequest(
        breakdown=_breakdown(task),
        requirements=_requirements("FR-001"),
        design=_design("api"),
    )

    export = WorkBreakdownExporter().export(request)
    rows = _parse_csv(export.csv_text)

    assert rows[0]["task"] == 'Add "quoted" task, with a comma'
    # RFC 4180: a field containing a comma or quote must be wrapped in
    # quotes, with embedded quotes doubled.
    assert '"Add ""quoted"" task, with a comma"' in export.csv_text


def test_export_reports_counts_and_coverage() -> None:
    request = WorkBreakdownExportRequest(
        breakdown=_breakdown(_task()),
        requirements=_requirements("FR-001"),
        design=_design("api"),
    )

    export = WorkBreakdownExporter().export(request)

    assert export.feature_count == 1
    assert export.story_count == 1
    assert export.task_count == 1
    assert export.covered_requirement_ids == ["FR-001"]
    assert export.covered_architecture_ids == ["api"]
    assert export.unmapped_requirement_ids == []
    assert export.unmapped_architecture_ids == []
    assert export.fabricated_requirement_ids == []
    assert export.fabricated_architecture_ids == []


def test_export_reports_unmapped_ids_from_the_upstream_artifacts() -> None:
    request = WorkBreakdownExportRequest(
        breakdown=_breakdown(
            _task(requirement_ids=["FR-001"], architecture_ids=["api"])
        ),
        requirements=_requirements("FR-001", "FR-002"),
        design=_design("api", "worker"),
    )

    export = WorkBreakdownExporter().export(request)

    assert export.unmapped_requirement_ids == ["FR-002"]
    assert export.unmapped_architecture_ids == ["worker"]


def test_export_reports_fabricated_ids_as_warnings_not_coverage() -> None:
    """A work item referencing an ID that doesn't exist in the upstream
    artifacts is a specification violation (never fabricate an ID) - it
    must be surfaced, not silently counted as covered."""

    request = WorkBreakdownExportRequest(
        breakdown=_breakdown(
            _task(requirement_ids=["FR-999"], architecture_ids=["ghost"])
        ),
        requirements=_requirements("FR-001"),
        design=_design("api"),
    )

    export = WorkBreakdownExporter().export(request)

    assert export.fabricated_requirement_ids == ["FR-999"]
    assert export.fabricated_architecture_ids == ["ghost"]
    assert export.covered_requirement_ids == []
    assert export.covered_architecture_ids == []
    assert any("FR-999" in warning for warning in export.warnings)
    assert any("ghost" in warning for warning in export.warnings)


def test_export_raises_when_a_task_has_no_traceability_at_all() -> None:
    request = WorkBreakdownExportRequest(
        breakdown=_breakdown(_task(requirement_ids=[], architecture_ids=[])),
        requirements=_requirements("FR-001"),
        design=_design("api"),
    )

    with pytest.raises(WorkBreakdownExportError, match="no requirement_ids"):
        WorkBreakdownExporter().export(request)


def test_export_warns_on_features_and_stories_with_no_children() -> None:
    breakdown = WorkBreakdownArtifact(
        features=[
            WorkBreakdownFeature(feature="Empty Feature", stories=[]),
            WorkBreakdownFeature(
                feature="Customer Management",
                stories=[WorkBreakdownStory(story="Empty Story", tasks=[])],
            ),
        ]
    )
    request = WorkBreakdownExportRequest(
        breakdown=breakdown,
        requirements=_requirements("FR-001"),
        design=_design("api"),
    )

    export = WorkBreakdownExporter().export(request)

    assert any("Empty Feature" in warning for warning in export.warnings)
    assert any("Empty Story" in warning for warning in export.warnings)


def test_export_passes_through_ambiguities() -> None:
    breakdown = _breakdown(_task())
    breakdown.ambiguities = [
        WorkBreakdownAmbiguity(
            kind="conflicting_inputs",
            description="Requirement FR-001 conflicts with component api.",
            related_ids=["FR-001", "api"],
        )
    ]
    request = WorkBreakdownExportRequest(
        breakdown=breakdown,
        requirements=_requirements("FR-001"),
        design=_design("api"),
    )

    export = WorkBreakdownExporter().export(request)

    assert export.ambiguities == breakdown.ambiguities
    assert any("conflicts with component api" in warning for warning in export.warnings)
