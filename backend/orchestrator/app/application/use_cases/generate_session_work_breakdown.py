"""Session-level work breakdown orchestration: generate/refine + persist.

Same relationship to ``GenerateWorkBreakdownUseCase`` that
``app.design.session.ArchitectureSession`` has to
``GenerateSystemDesignUseCase`` - that use case is pure agent orchestration
against a port, with no idea a "session" or versioned Blob storage exists;
this module is the thin layer above it that bumps a version number and
persists the result, so ``app/api/routes/work_breakdown.py`` doesn't have
to duplicate that bookkeeping across ``generate``/``refine``.

Deliberately *not* responsible for checking "is the architecture approved
yet" or "does a work breakdown already exist" - those are session-state
questions the route already has ``SessionRecord`` in hand to answer itself
(see ``_require_stage``/the approval-status check in
``app/api/routes/work_breakdown.py``), the same split
``ArchitectureSession`` and ``accept_run``/``refine_architecture`` already
have: the route decides *whether* to call this, this decides *how*.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.application.ports import ArtifactStorePort, WorkBreakdownExporterPort
from app.application.use_cases.generate_work_breakdown import (
    GenerateWorkBreakdownUseCase,
)
from app.domain.design import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact
from app.domain.work_breakdown import WorkBreakdownArtifact, WorkBreakdownExport


class WorkBreakdownSessionResult:
    """Result of generating/refining a work breakdown for a session."""

    breakdown: WorkBreakdownArtifact
    breakdown_blob: str
    version: int
    created_at: str

    def __init__(
        self,
        breakdown: WorkBreakdownArtifact,
        breakdown_blob: str,
        version: int,
    ) -> None:
        self.breakdown = breakdown
        self.breakdown_blob = breakdown_blob
        self.version = version
        self.created_at = datetime.now(UTC).isoformat()


@dataclass(slots=True)
class GenerateSessionWorkBreakdownUseCase:
    """Generate (or refine) a work breakdown and persist it as a new,
    immutable version - the work-breakdown analogue of
    ``ArchitectureSession.generate``/``generate_from_design``.
    """

    generator: GenerateWorkBreakdownUseCase
    artifact_store: ArtifactStorePort

    async def execute(
        self,
        session_id: str,
        version: int,
        requirements: RequirementsArtifact,
        design: SystemDesignArtifact,
        previous_breakdown: WorkBreakdownArtifact | None = None,
        refinement_input: str | None = None,
    ) -> WorkBreakdownSessionResult:
        """Return a persisted ``WorkBreakdownSessionResult`` for ``session_id``.

        ``version`` is the session's *current* ``work_breakdown_version``
        (``0`` for a brand-new breakdown) - the next version persisted is
        ``version + 1``, mirroring ``ArchitectureSession``'s own
        ``self.version + 1`` convention. Passing ``previous_breakdown``/
        ``refinement_input`` refines that breakdown instead of generating a
        fresh one - see ``GenerateWorkBreakdownUseCase.execute``.

        Raises ``ValueError`` (missing requirements/components) or
        ``app.application.errors.WorkBreakdownGenerationError`` (agent
        failure), exactly as ``GenerateWorkBreakdownUseCase.execute`` does -
        this adds no error translation of its own, unlike
        ``ArchitectureSession`` (which wraps several distinct failure modes
        into one ``DesignGenerationWorkflowError``); there's only one
        upstream call here to fail.
        """

        breakdown = await self.generator.execute(
            requirements,
            design,
            previous_breakdown=previous_breakdown,
            refinement_input=refinement_input,
        )

        next_version = version + 1
        breakdown_blob = self.artifact_store.save_work_breakdown_json(
            session_id=session_id,
            version=next_version,
            content=breakdown.model_dump_json(indent=2),
        )

        return WorkBreakdownSessionResult(
            breakdown=breakdown,
            breakdown_blob=breakdown_blob,
            version=next_version,
        )


class WorkBreakdownExportSessionResult:
    """Result of exporting a session's current work breakdown to CSV.

    Same "carry the blob pointer back to the caller" shape as
    ``WorkBreakdownSessionResult`` above - the route needs
    ``export_blob`` to stamp ``SessionRecord.work_breakdown_export_blob``
    (see ``app/domain/session.py``), not just the rendered CSV text.
    """

    export: WorkBreakdownExport
    export_blob: str

    def __init__(self, export: WorkBreakdownExport, export_blob: str) -> None:
        self.export = export
        self.export_blob = export_blob


@dataclass(slots=True)
class ExportSessionWorkBreakdownUseCase:
    """Render a session's current work breakdown to CSV and cache it.

    The export analogue of ``GenerateSessionWorkBreakdownUseCase`` above:
    validates ``breakdown`` against ``requirements``/``design`` and renders
    it to CSV via the injected ``WorkBreakdownExporterPort``
    (``app.infrastructure.tools_client.McpToolsClient``), then persists the
    CSV text so a later fetch of the same version doesn't have to re-render
    it. Unlike the JSON breakdown itself, the CSV is a derived,
    re-computable artifact - see ``ArtifactStorePort
    .save_work_breakdown_csv`` for why re-exporting the same version
    overwrites rather than conflicts.
    """

    exporter: WorkBreakdownExporterPort
    artifact_store: ArtifactStorePort

    def execute(
        self,
        session_id: str,
        version: int,
        breakdown: WorkBreakdownArtifact,
        requirements: RequirementsArtifact,
        design: SystemDesignArtifact,
    ) -> WorkBreakdownExportSessionResult:
        """Return a ``WorkBreakdownExportSessionResult`` for ``breakdown``.

        Raises ``app.application.errors.WorkBreakdownExportError`` if the
        tools-service call fails - no translation here either, same
        reasoning as ``GenerateSessionWorkBreakdownUseCase.execute``.
        """

        export = self.exporter.export(breakdown, requirements, design)

        export_blob = self.artifact_store.save_work_breakdown_csv(
            session_id=session_id,
            version=version,
            content=export.csv_text,
        )

        return WorkBreakdownExportSessionResult(
            export=export,
            export_blob=export_blob,
        )
