"""Classify an uploaded image as a document screenshot or a diagram."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.ports import ImageClassifierPort
from app.domain.vision import ImageClassification


@dataclass(slots=True)
class ClassifyImageUseCase:
    """Thin orchestration wrapper around an ``ImageClassifierPort``.

    Exists mainly for symmetry with ``AnalyzeRequirementsUseCase``/
    ``GenerateSystemDesignUseCase`` — a single place the presentation
    layer depends on, so which concrete agent classifies an image is an
    infrastructure concern the API layer never sees.
    """

    agent: ImageClassifierPort

    async def execute(self, content: bytes, filename: str) -> ImageClassification:
        return await self.agent.classify(content, filename)
