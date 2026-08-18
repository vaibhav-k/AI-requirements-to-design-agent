"""Vision-related domain value objects.

See ``app/vision.py``'s module docstring for the wider story this
belongs to: an uploaded image is either a screenshot of text (handled by
the normal requirements/OCR pipeline) or a system design/workflow
diagram (interpreted directly into a ``SystemDesignArtifact`` — see
``app.design.models``, not yet moved into this package — via
``app.application.ports.DiagramImageInterpreterPort``).

Moved here, verbatim, from ``app/vision.py`` as part of the Clean
Architecture migration (see README -> "Clean Architecture Migration") —
the same "pure entity, zero I/O" home ``app.domain.requirements`` already
gives ``Requirement``/``RequirementsArtifact``/etc.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ImageClassification(BaseModel):
    """Result of classifying an uploaded image — see the module docstring."""

    kind: Literal["document", "diagram"]
    reasoning: str = Field(
        description="One sentence explaining why this image was classified this way."
    )
