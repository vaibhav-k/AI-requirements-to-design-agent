"""Error types raised by tools-service's deterministic operations.

Mirrors the relevant subset of the orchestrator's
``app.application.errors`` - see ``src/domain/design.py``'s module
docstring for why this is a deliberate duplication rather than a shared
package.
"""

from __future__ import annotations


class DiagramGenerationError(RuntimeError):
    """Raised when rendering a design to a diagram fails.

    Raised by ``src.infrastructure.diagram.ArchitectureDiagramGenerator``.
    """


class ArchitectureValidationError(ValueError):
    """Raised when an architecture fails semantic validation.

    Raised by ``src.infrastructure.validator.ArchitectureValidator``.
    """


class WorkBreakdownExportError(ValueError):
    """Raised when a work breakdown fails structural validation and can't
    be safely exported to CSV.

    Raised by ``src.infrastructure.work_breakdown_export.WorkBreakdownExporter``
    - the work-breakdown analogue of ``ArchitectureValidationError``. Only
    for defects that make the CSV meaningless (e.g. a task with no
    traceability to any requirement or architecture ID at all); everything
    else recoverable is surfaced as a warning on the returned
    ``WorkBreakdownExport`` instead.
    """


class TechnicalDesignExportError(ValueError):
    """Raised when a technical design document fails structural
    validation and can't be safely rendered to ``.docx``.

    Raised by ``src.infrastructure.document_export.TechnicalDesignExporter``
    - the technical-design analogue of ``WorkBreakdownExportError``. Only
    for defects that make the document meaningless (e.g. no sections at
    all); everything else recoverable (e.g. the diagram failing to
    render) is surfaced as a warning on the returned
    ``TechnicalDesignExport`` instead.
    """
