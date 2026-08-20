"""Error types raised by tools-service's deterministic operations.

Mirrors the relevant subset of the orchestrator's
``app.application.errors`` — see ``src/domain/design.py``'s module
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
