"""Classify an uploaded image as a document screenshot or a diagram.

An uploaded image can mean two very different things to this pipeline:

* A screenshot or photo of TEXT - requirements notes, a spec, an email, a
  whiteboard of bullet points - meant to be *read*. These already go
  through OCR (``app/ingestion.py``'s Document Intelligence extraction)
  and into the normal requirements-analysis pipeline.
* A photo or screenshot of a SYSTEM DESIGN / WORKFLOW DIAGRAM - boxes and
  arrows depicting components, services, or data flow - meant to be
  *understood structurally*, not read as prose. Running OCR + requirements
  analysis on this would, at best, transcribe box labels as if they were
  requirements text, and at worst produce nonsense.

``ClassifyImageUseCase`` decides which of the two an uploaded image is.
``InterpretDiagramImageUseCase`` (see ``interpret_diagram_image.py``)
handles the second case: it derives a structured ``SystemDesignArtifact``
directly from the image - "redraw this as a clean, well-architected
system design" - reusing the exact schema ``GenerateSystemDesignUseCase``
produces from text, so everything downstream (validation, diagram
rendering, versioning, refinement, approval) treats an image-derived
design exactly like a text-derived one. See
``app/api/routes/requirements.py``'s upload routes for how the two are
wired together.

(This docstring used to live on ``app/vision.py``, the deleted "strangler
fig" facade both use cases were bridged through before Clean Architecture
Migration Slice 6 - see the README.)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.ports import ImageClassifierPort
from app.domain.vision import ImageClassification


@dataclass(slots=True)
class ClassifyImageUseCase:
    """Thin orchestration wrapper around an ``ImageClassifierPort``.

    Exists mainly for symmetry with ``AnalyzeRequirementsUseCase``/
    ``GenerateSystemDesignUseCase`` - a single place the presentation
    layer depends on, so which concrete agent classifies an image is an
    infrastructure concern the API layer never sees.
    """

    agent: ImageClassifierPort

    async def execute(self, content: bytes, filename: str) -> ImageClassification:
        return await self.agent.classify(content, filename)
