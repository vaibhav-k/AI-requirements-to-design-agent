"""Backward-compatible synchronous facade for image input classification.

An uploaded image can mean two very different things to this pipeline:

* A screenshot or photo of TEXT — requirements notes, a spec, an email, a
  whiteboard of bullet points — meant to be *read*. These already go
  through OCR (``app/ingestion.py``'s Document Intelligence extraction)
  and into the normal requirements-analysis pipeline.
* A photo or screenshot of a SYSTEM DESIGN / WORKFLOW DIAGRAM — boxes and
  arrows depicting components, services, or data flow — meant to be
  *understood structurally*, not read as prose. Running OCR + requirements
  analysis on this would, at best, transcribe box labels as if they were
  requirements text, and at worst produce nonsense.

``ImageInputClassifier`` decides which of the two an uploaded image is.
``DiagramImageInterpreter`` handles the second case: it derives a
structured ``SystemDesignArtifact`` directly from the image — "redraw this
as a clean, well-architected system design" — reusing the exact schema
``SystemDesignAnalyzer`` (``app/design/analyzer.py``) produces from text,
so everything downstream (validation, diagram rendering, versioning,
refinement, approval) treats an image-derived design exactly like a
text-derived one. See ``app/api/routes/requirements.py``'s upload routes
for how the two are wired together.

As of this slice of the Clean Architecture migration (see README →
"Clean Architecture Migration"), the real work happens in:

* ``app.domain.vision`` — the ``ImageClassification`` entity (moved out
  of this module, verbatim)
* ``app.application.ports.ImageClassifierPort`` /
  ``DiagramImageInterpreterPort`` — the abstractions
* ``app.application.use_cases.classify_image.ClassifyImageUseCase`` /
  ``app.application.use_cases.interpret_diagram_image
  .InterpretDiagramImageUseCase`` — the orchestration
* ``app.infrastructure.agents.image_classifier_agent
  .AgentFrameworkImageClassifierAgent`` /
  ``app.infrastructure.agents.diagram_image_interpreter_agent
  .AgentFrameworkDiagramImageInterpreterAgent`` — the concrete adapters,
  now backed by Microsoft Agent Framework instead of a direct OpenAI SDK
  call (multimodal image input via ``agent_framework.Message``/
  ``Content`` — see either adapter's docstring for the full rationale)

``ImageInputClassifier``/``DiagramImageInterpreter`` exist only so the
existing synchronous call sites (``app/api/dependencies.py``) don't all
need to change in the same slice — the same "strangler fig" seam
``app/analyzer.py``/``app/design/analyzer.py`` use for requirements/design
analysis. New code should depend on ``ClassifyImageUseCase``/
``InterpretDiagramImageUseCase`` + their ports directly rather than
adding new usages of these facades.
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

from app.application.errors import DiagramInterpretationError, ImageClassificationError
from app.application.ports import DiagramImageInterpreterPort, ImageClassifierPort
from app.application.use_cases.classify_image import ClassifyImageUseCase
from app.application.use_cases.interpret_diagram_image import (
    InterpretDiagramImageUseCase,
)
from app.design.models import SystemDesignArtifact
from app.domain.vision import ImageClassification
from app.infrastructure.agents.diagram_image_interpreter_agent import (
    AgentFrameworkDiagramImageInterpreterAgent,
)
from app.infrastructure.agents.image_classifier_agent import (
    AgentFrameworkImageClassifierAgent,
)

load_dotenv()

__all__ = [
    "DiagramImageInterpreter",
    "DiagramInterpretationError",
    "ImageClassification",
    "ImageClassificationError",
    "ImageInputClassifier",
]


def _required_environment_variable(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"{name} environment variable is required.")

    return value


AZURE_OPENAI_API_KEY = _required_environment_variable("AZURE_OPENAI_API_KEY")

AZURE_OPENAI_ENDPOINT = _required_environment_variable("AZURE_OPENAI_ENDPOINT")

AZURE_OPENAI_MODEL = _required_environment_variable("AZURE_OPENAI_MODEL")


def _raise_if_running_loop(caller: str) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return

    raise RuntimeError(
        f"{caller}() cannot be called from a running event loop — "
        f"await {caller.split('.')[-1]}_async() instead."
    )


class ImageInputClassifier:
    """Classifies an uploaded image as a document screenshot or a system
    design/workflow diagram (sync facade)."""

    def __init__(
        self,
        model: str = AZURE_OPENAI_MODEL,
        agent: ImageClassifierPort | None = None,
    ) -> None:
        """``agent`` is injectable — pass a fake/mock ``ImageClassifierPort``
        in tests instead of constructing a real Microsoft Agent Framework
        agent (and therefore requiring live Azure OpenAI credentials)."""

        resolved_agent: ImageClassifierPort = agent or (
            AgentFrameworkImageClassifierAgent(
                api_key=AZURE_OPENAI_API_KEY,
                endpoint=AZURE_OPENAI_ENDPOINT,
                model=model,
            )
        )

        self._use_case = ClassifyImageUseCase(agent=resolved_agent)

    async def classify_async(
        self, content: bytes, filename: str
    ) -> ImageClassification:
        """The native, non-bridged entry point — use this from any
        ``async def`` caller (e.g. ``app/api/routes/requirements.py``'s
        upload routes, which already run on the event loop) instead of
        ``classify()``, which cannot be called from inside a running
        event loop."""

        return await self._use_case.execute(content, filename)

    def classify(self, content: bytes, filename: str) -> ImageClassification:
        """Classify ``content`` (an uploaded image's raw bytes) as a
        ``"document"`` screenshot or a ``"diagram"``.

        Synchronous on purpose — see ``RequirementsAnalyzer.analyze``'s
        docstring for why, and why this raises ``RuntimeError`` instead
        of deadlocking/crashing confusingly if called from a running
        event loop.
        """

        _raise_if_running_loop("ImageInputClassifier.classify")

        return asyncio.run(self._use_case.execute(content, filename))


class DiagramImageInterpreter:
    """Derives a structured system design directly from a diagram image
    (sync facade)."""

    def __init__(
        self,
        model: str = AZURE_OPENAI_MODEL,
        agent: DiagramImageInterpreterPort | None = None,
    ) -> None:
        """``agent`` is injectable — pass a fake/mock
        ``DiagramImageInterpreterPort`` in tests instead of constructing a
        real Microsoft Agent Framework agent (and therefore requiring live
        Azure OpenAI credentials)."""

        resolved_agent: DiagramImageInterpreterPort = agent or (
            AgentFrameworkDiagramImageInterpreterAgent(
                api_key=AZURE_OPENAI_API_KEY,
                endpoint=AZURE_OPENAI_ENDPOINT,
                model=model,
            )
        )

        self._use_case = InterpretDiagramImageUseCase(agent=resolved_agent)

    async def interpret_async(
        self,
        content: bytes,
        filename: str,
        previous_design: SystemDesignArtifact | None = None,
        notes: str | None = None,
    ) -> SystemDesignArtifact:
        """The native, non-bridged entry point — use this from any
        ``async def`` caller instead of ``interpret()``, which cannot be
        called from inside a running event loop."""

        return await self._use_case.execute(
            content,
            filename,
            previous_design=previous_design,
            notes=notes,
        )

    def interpret(
        self,
        content: bytes,
        filename: str,
        previous_design: SystemDesignArtifact | None = None,
        notes: str | None = None,
    ) -> SystemDesignArtifact:
        """Interpret ``content`` (an uploaded diagram image's raw bytes)
        into a redrawn, well-architected ``SystemDesignArtifact``.

        Passing ``previous_design`` treats the image as refining that
        design rather than replacing it wholesale, the same "preserve what
        still applies" contract ``SystemDesignAnalyzer.analyze`` follows
        for text-based refinement.

        Synchronous on purpose — see ``RequirementsAnalyzer.analyze``'s
        docstring for why, and why this raises ``RuntimeError`` instead
        of deadlocking/crashing confusingly if called from a running
        event loop.
        """

        _raise_if_running_loop("DiagramImageInterpreter.interpret")

        return asyncio.run(
            self._use_case.execute(
                content,
                filename,
                previous_design=previous_design,
                notes=notes,
            )
        )
