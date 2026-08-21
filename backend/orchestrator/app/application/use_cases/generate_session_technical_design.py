"""Session-level technical design orchestration: generate/refine/export +
persist.

Same relationship to ``GenerateTechnicalDesignUseCase`` that
``generate_session_work_breakdown.py``'s
``GenerateSessionWorkBreakdownUseCase`` has to
``GenerateWorkBreakdownUseCase`` - that use case is pure agent
orchestration against a port, with no idea a "session" or versioned Blob
storage exists; this module is the thin layer above it that bumps a
version number and persists the result, so
``app/api/routes/technical_design.py`` doesn't have to duplicate that
bookkeeping across ``generate``/``refine``/``export``.

Deliberately *not* responsible for checking "has the session reached the
work_breakdown stage" or "does a document already exist" - those are
session-state questions the route already has ``SessionRecord`` in hand
to answer itself, the same split ``GenerateSessionWorkBreakdownUseCase``
already has with its own route.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime

from app.application.ports import ArtifactStorePort, DocumentExporterPort
from app.application.use_cases.generate_technical_design import (
    GenerateTechnicalDesignUseCase,
)
from app.domain.design import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact
from app.domain.technical_design import TechnicalDesignArtifact, TechnicalDesignExport
from app.domain.work_breakdown import WorkBreakdownArtifact


class TechnicalDesignSessionResult:
    """Result of generating/refining a technical design document for a
    session."""

    document: TechnicalDesignArtifact
    document_blob: str
    version: int
    created_at: str

    def __init__(
        self,
        document: TechnicalDesignArtifact,
        document_blob: str,
        version: int,
    ) -> None:
        self.document = document
        self.document_blob = document_blob
        self.version = version
        self.created_at = datetime.now(UTC).isoformat()


@dataclass(slots=True)
class GenerateSessionTechnicalDesignUseCase:
    """Generate (or refine) a technical design document and persist it as
    a new, immutable version - the technical-design analogue of
    ``GenerateSessionWorkBreakdownUseCase``.
    """

    generator: GenerateTechnicalDesignUseCase
    artifact_store: ArtifactStorePort

    async def execute(
        self,
        session_id: str,
        version: int,
        requirements: RequirementsArtifact,
        design: SystemDesignArtifact,
        work_breakdown: WorkBreakdownArtifact,
        previous_document: TechnicalDesignArtifact | None = None,
        refinement_input: str | None = None,
    ) -> TechnicalDesignSessionResult:
        """Return a persisted ``TechnicalDesignSessionResult`` for
        ``session_id``.

        ``version`` is the session's *current* ``technical_design_version``
        (``0`` for a brand-new document) - the next version persisted is
        ``version + 1``, mirroring ``GenerateSessionWorkBreakdownUseCase``'s
        own convention. Passing ``previous_document``/``refinement_input``
        refines that document instead of generating a fresh one - see
        ``GenerateTechnicalDesignUseCase.execute``.

        Raises ``ValueError`` (missing components/features) or
        ``app.application.errors.TechnicalDesignGenerationError`` (agent
        failure), exactly as ``GenerateTechnicalDesignUseCase.execute``
        does - this adds no error translation of its own.
        """

        document = await self.generator.execute(
            requirements,
            design,
            work_breakdown,
            previous_document=previous_document,
            refinement_input=refinement_input,
        )

        next_version = version + 1
        document_blob = self.artifact_store.save_technical_design_json(
            session_id=session_id,
            version=next_version,
            content=document.model_dump_json(indent=2),
        )

        return TechnicalDesignSessionResult(
            document=document,
            document_blob=document_blob,
            version=next_version,
        )


class TechnicalDesignExportSessionResult:
    """Result of exporting a session's current technical design document
    to ``.docx``.

    Same "carry the blob pointer back to the caller" shape as
    ``TechnicalDesignSessionResult`` above - the route needs
    ``export_blob`` to stamp ``SessionRecord.technical_design_export_blob``
    (see ``app/domain/session.py``), not just the rendered file.
    """

    export: TechnicalDesignExport
    export_blob: str

    def __init__(self, export: TechnicalDesignExport, export_blob: str) -> None:
        self.export = export
        self.export_blob = export_blob


@dataclass(slots=True)
class ExportSessionTechnicalDesignUseCase:
    """Render a session's current technical design document to ``.docx``
    and cache it.

    The export analogue of ``GenerateSessionTechnicalDesignUseCase``
    above: renders ``document`` (with ``design``'s diagram embedded) via
    the injected ``DocumentExporterPort``
    (``app.infrastructure.tools_client.McpToolsClient``), then persists
    the file bytes so a later fetch of the same version doesn't have to
    re-render it. Unlike the JSON document itself, the ``.docx`` is a
    derived, re-computable artifact - see ``ArtifactStorePort
    .save_technical_design_docx`` for why re-exporting the same version
    overwrites rather than conflicts.
    """

    exporter: DocumentExporterPort
    artifact_store: ArtifactStorePort

    def execute(
        self,
        session_id: str,
        version: int,
        document: TechnicalDesignArtifact,
        design: SystemDesignArtifact,
        requirements: RequirementsArtifact,
        work_breakdown: WorkBreakdownArtifact,
    ) -> TechnicalDesignExportSessionResult:
        """Return a ``TechnicalDesignExportSessionResult`` for ``document``.

        Raises ``app.application.errors.TechnicalDesignExportError`` if
        the tools-service call fails - no translation here either, same
        reasoning as ``GenerateSessionTechnicalDesignUseCase.execute``.
        """

        export = self.exporter.export_document(
            document, design, requirements, work_breakdown
        )

        # `export.docx_base64` is base64 *text* (the MCP transport
        # envelope's JSON has no binary type) - decode back to the actual
        # `.docx` bytes before handing them to Blob Storage, rather than
        # persisting the base64 text itself as the "file".
        export_blob = self.artifact_store.save_technical_design_docx(
            session_id=session_id,
            version=version,
            content=base64.b64decode(export.docx_base64),
        )

        return TechnicalDesignExportSessionResult(
            export=export,
            export_blob=export_blob,
        )
