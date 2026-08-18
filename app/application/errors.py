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
