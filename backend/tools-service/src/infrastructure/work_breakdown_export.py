"""Deterministic, LLM-free work-breakdown CSV export + traceability
validation.

The work-breakdown analogue of ``validator.py``: pure logic, no I/O, no
Azure OpenAI dependency, moved here (rather than living in-process on the
orchestrator) for the same reason ``ArchitectureValidator`` and
``ArchitectureDiagramGenerator`` are - see ``src/domain/design.py``'s
module docstring and the root README's "Service Architecture" section.

``export`` never invents a relationship the upstream requirements/
architecture didn't support: every requirement/architecture ID a work
item references is checked against the actual
``RequirementsArtifact``/``SystemDesignArtifact`` it claims to trace to,
and every requirement/architecture ID *not* referenced by any work item
is reported back rather than silently dropped - see the Work Breakdown
Agent specification's "no fabricated IDs" / "no missing
implementation-relevant requirements or architecture elements" rules.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from src.domain.errors import WorkBreakdownExportError
from src.domain.work_breakdown import (
    WorkBreakdownArtifact,
    WorkBreakdownExport,
    WorkBreakdownExportRequest,
)

__all__ = ["WorkBreakdownExportError", "WorkBreakdownExporter"]

CSV_COLUMNS = [
    "feature",
    "story",
    "task",
    "description",
    "effort",
    "requirement_ids",
    "architecture_ids",
]


@dataclass(frozen=True, slots=True)
class _Row:
    """One flattened Task, ready to become one CSV row."""

    feature: str
    story: str
    task: str
    description: str
    effort: str
    requirement_ids: list[str]
    architecture_ids: list[str]


class WorkBreakdownExporter:
    """Validate a work breakdown's traceability and render it to CSV.

    ``export`` itself only assembles the pieces and raises on a hard
    structural defect - each check lives in its own small, independently
    testable method, the same shape ``ArchitectureValidator`` uses.
    """

    def export(self, request: WorkBreakdownExportRequest) -> WorkBreakdownExport:
        """Validate and export ``request.breakdown``.

        Raises ``WorkBreakdownExportError`` if any task has no
        traceability to a requirement or architecture ID at all - every
        other defect is reported as a warning instead, since it doesn't
        make the CSV meaningless, just imperfect.
        """

        rows = self._flatten(request.breakdown)

        errors = self._untraceable_task_errors(rows)
        if errors:
            raise WorkBreakdownExportError(
                "Work breakdown validation failed:\n- " + "\n- ".join(errors)
            )

        valid_requirement_ids = {
            requirement.id
            for requirement in (
                *request.requirements.functional_requirements,
                *request.requirements.non_functional_requirements,
            )
        }
        valid_architecture_ids = {
            *(component.id for component in request.design.components),
            *(interface.id for interface in request.design.interfaces),
            *(dependency.id for dependency in request.design.external_dependencies),
        }

        referenced_requirement_ids = {
            requirement_id for row in rows for requirement_id in row.requirement_ids
        }
        referenced_architecture_ids = {
            architecture_id for row in rows for architecture_id in row.architecture_ids
        }

        covered_requirement_ids = sorted(
            referenced_requirement_ids & valid_requirement_ids
        )
        covered_architecture_ids = sorted(
            referenced_architecture_ids & valid_architecture_ids
        )
        fabricated_requirement_ids = sorted(
            referenced_requirement_ids - valid_requirement_ids
        )
        fabricated_architecture_ids = sorted(
            referenced_architecture_ids - valid_architecture_ids
        )
        unmapped_requirement_ids = sorted(
            valid_requirement_ids - referenced_requirement_ids
        )
        unmapped_architecture_ids = sorted(
            valid_architecture_ids - referenced_architecture_ids
        )

        warnings = self._structural_warnings(request.breakdown, rows)
        warnings.extend(
            self._fabrication_warnings(
                fabricated_requirement_ids, fabricated_architecture_ids
            )
        )

        return WorkBreakdownExport(
            csv_text=self._render_csv(rows),
            feature_count=len(request.breakdown.features),
            story_count=sum(
                len(feature.stories) for feature in request.breakdown.features
            ),
            task_count=len(rows),
            covered_requirement_ids=covered_requirement_ids,
            covered_architecture_ids=covered_architecture_ids,
            unmapped_requirement_ids=unmapped_requirement_ids,
            unmapped_architecture_ids=unmapped_architecture_ids,
            fabricated_requirement_ids=fabricated_requirement_ids,
            fabricated_architecture_ids=fabricated_architecture_ids,
            ambiguities=request.breakdown.ambiguities,
            warnings=warnings,
        )

    # ---------------------------------------------------------
    # Flattening
    # ---------------------------------------------------------

    @staticmethod
    def _flatten(breakdown: WorkBreakdownArtifact) -> list[_Row]:
        return [
            _Row(
                feature=feature.feature,
                story=story.story,
                task=task.task,
                description=task.description,
                effort=task.effort,
                requirement_ids=task.requirement_ids,
                architecture_ids=task.architecture_ids,
            )
            for feature in breakdown.features
            for story in feature.stories
            for task in story.tasks
        ]

    # ---------------------------------------------------------
    # Hard failures
    # ---------------------------------------------------------

    @staticmethod
    def _untraceable_task_errors(rows: list[_Row]) -> list[str]:
        """Every task must reference at least one requirement or
        architecture ID - see the specification's traceability rule 3."""

        return [
            f"Task '{row.task}' (story '{row.story}', feature '{row.feature}') "
            "has no traceability: no requirement_ids and no architecture_ids."
            for row in rows
            if not row.requirement_ids and not row.architecture_ids
        ]

    # ---------------------------------------------------------
    # Warnings
    # ---------------------------------------------------------

    @staticmethod
    def _structural_warnings(
        breakdown: WorkBreakdownArtifact, rows: list[_Row]
    ) -> list[str]:
        warnings: list[str] = []

        if not breakdown.features:
            warnings.append("The work breakdown contains no features.")

        feature_names = [feature.feature for feature in breakdown.features]
        duplicate_features = sorted(
            {name for name in feature_names if feature_names.count(name) > 1}
        )
        if duplicate_features:
            warnings.append(
                "Duplicate feature name(s) - merge into a single feature "
                f"with multiple stories instead: {', '.join(duplicate_features)}."
            )

        for feature in breakdown.features:
            if not feature.stories:
                warnings.append(f"Feature '{feature.feature}' has no stories.")
            for story in feature.stories:
                if not story.tasks:
                    warnings.append(
                        f"Story '{story.story}' (feature '{feature.feature}') "
                        "has no tasks."
                    )

        for ambiguity in breakdown.ambiguities:
            warnings.append(f"[{ambiguity.kind}] {ambiguity.description}")

        return warnings

    @staticmethod
    def _fabrication_warnings(
        fabricated_requirement_ids: list[str],
        fabricated_architecture_ids: list[str],
    ) -> list[str]:
        warnings: list[str] = []

        if fabricated_requirement_ids:
            warnings.append(
                "Work items reference requirement ID(s) that do not exist "
                "in the supplied requirements: "
                f"{', '.join(fabricated_requirement_ids)}."
            )

        if fabricated_architecture_ids:
            warnings.append(
                "Work items reference architecture ID(s) that do not exist "
                "in the supplied architecture: "
                f"{', '.join(fabricated_architecture_ids)}."
            )

        return warnings

    # ---------------------------------------------------------
    # CSV rendering
    # ---------------------------------------------------------

    @staticmethod
    def _render_csv(rows: list[_Row]) -> str:
        """Render ``rows`` as an RFC 4180-compliant CSV document.

        ``csv.writer`` with the default ``QUOTE_MINIMAL`` dialect already
        quotes any field containing a comma, quote, or line break and
        doubles embedded double quotes, satisfying the specification's
        escaping rules without hand-rolled quoting logic.
        """

        buffer = io.StringIO()
        writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        writer.writerow(CSV_COLUMNS)

        for row in rows:
            writer.writerow(
                [
                    row.feature,
                    row.story,
                    row.task,
                    row.description,
                    row.effort,
                    ",".join(row.requirement_ids),
                    ",".join(row.architecture_ids),
                ]
            )

        return buffer.getvalue()
