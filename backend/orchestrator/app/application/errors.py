"""Shared application-layer error types.

Kept separate from any single use case since more than one may need to
raise/catch the same failure category - e.g. both
``GenerateSystemDesignUseCase`` (fresh generation) and its own
refinement path (same use case, ``previous_design`` supplied) should
raise one exception type, not near-duplicate ones per call shape.
"""

from __future__ import annotations


class DesignGenerationError(RuntimeError):
    """Raised when architecture generation or refinement fails."""


class ImageClassificationError(RuntimeError):
    """Raised when an uploaded image can't be classified."""


class DiagramInterpretationError(RuntimeError):
    """Raised when a diagram image can't be interpreted into an architecture."""


class ArtifactVersionConflict(RuntimeError):
    """Raised by ``ArtifactStorePort.save_design_json`` when that version
    already exists - versions are immutable once written (see
    ``app.infrastructure.artifact_store.ArtifactStore``), so a second write
    to the same version number is a conflict, not an overwrite."""


class SessionConflictError(RuntimeError):
    """Raised when ``SessionStorePort.upsert`` loses a race against another
    writer.

    Surfaces a concurrency-token mismatch (a Cosmos ETag/HTTP 412, for
    ``app.infrastructure.session_store.CosmosSessionStore``) as a
    store-level error the caller can translate into whatever response
    makes sense for it - an HTTP 409 in the web routes - without the
    routes needing to know anything about Cosmos or ETags directly.
    """


class DiagramGenerationError(RuntimeError):
    """Raised when ``DiagramRendererPort.generate`` fails to render a design.

    As of the tools-service split (see README -> "Service Architecture"),
    the concrete ``DiagramRendererPort`` implementation is
    ``app.infrastructure.tools_client.McpToolsClient``, which raises this
    when the remote call to ``backend/tools-service`` (via
    ``backend/mcp-wrapper``) fails or reports a rendering error - the same
    exception type ``app.design.diagram.ArchitectureDiagramGenerator``
    used to raise when rendering happened in-process, before the split.
    Caught by ``app.design.session.ArchitectureSession`` (wrapped into a
    ``DesignGenerationWorkflowError``) and by ``app/main.py``'s CLI loop
    directly.
    """


class ArchitectureValidationError(ValueError):
    """Raised when an architecture fails semantic validation.

    As of the tools-service split (see README -> "Service Architecture"),
    the concrete ``ArchitectureValidatorPort`` implementation is
    ``app.infrastructure.tools_client.McpToolsClient``, which raises this
    when the remote call to ``backend/tools-service`` (via
    ``backend/mcp-wrapper``) reports a validation failure - the same
    exception type ``app.design.validator.ArchitectureValidator`` used to
    raise when validation happened in-process, before the split. Moved
    here (from the former ``app.design.validator`` module, which no
    longer exists on the orchestrator) since it's a cross-cutting
    application error like ``DiagramGenerationError`` above, not specific
    to any one module.
    """


class WorkBreakdownGenerationError(RuntimeError):
    """Raised when work-breakdown generation or refinement fails.

    Raised by ``app.infrastructure.agents.work_breakdown_agent
    .AgentFrameworkWorkBreakdownAgent`` - the work-breakdown analogue of
    ``DesignGenerationError``.
    """


class WorkBreakdownExportError(RuntimeError):
    """Raised when ``WorkBreakdownExporterPort.export`` fails to render a
    work breakdown to CSV.

    Raised by ``app.infrastructure.tools_client.McpToolsClient`` when the
    remote call to ``backend/tools-service`` (via ``backend/mcp-wrapper``)
    fails or reports an export/validation failure - the work-breakdown
    analogue of ``DiagramGenerationError``/``ArchitectureValidationError``
    above.
    """


class TechnicalDesignGenerationError(RuntimeError):
    """Raised when technical-design-document generation or refinement fails.

    Raised by ``app.infrastructure.agents.technical_writer_agent
    .AgentFrameworkTechnicalWriterAgent`` - the technical-design analogue
    of ``WorkBreakdownGenerationError``.
    """


class TechnicalDesignExportError(RuntimeError):
    """Raised when ``DocumentExporterPort.export`` fails to render a
    technical design document to ``.docx``.

    Raised by ``app.infrastructure.tools_client.McpToolsClient`` when the
    remote call to ``backend/tools-service`` (via ``backend/mcp-wrapper``)
    fails or reports a rendering failure - the technical-design analogue
    of ``WorkBreakdownExportError``.
    """
