"""Shared application-layer error types.

Kept separate from any single use case since more than one may need to
raise/catch the same failure category — e.g. both
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
    already exists — versions are immutable once written (see
    ``app.infrastructure.artifact_store.ArtifactStore``), so a second write
    to the same version number is a conflict, not an overwrite."""


class SessionConflictError(RuntimeError):
    """Raised when ``SessionStorePort.upsert`` loses a race against another
    writer.

    Surfaces a concurrency-token mismatch (a Cosmos ETag/HTTP 412, for
    ``app.infrastructure.session_store.CosmosSessionStore``) as a
    store-level error the caller can translate into whatever response
    makes sense for it — an HTTP 409 in the web routes — without the
    routes needing to know anything about Cosmos or ETags directly.
    """


class DiagramGenerationError(RuntimeError):
    """Raised when ``DiagramRendererPort.generate`` fails to render a design.

    Raised by ``app.design.diagram.ArchitectureDiagramGenerator``, the
    concrete ``DiagramRendererPort`` implementation, and caught by
    ``app.design.session.ArchitectureSession`` (wrapped into a
    ``DesignGenerationWorkflowError``) and by ``app/main.py``'s CLI loop
    directly.
    """
