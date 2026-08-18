"""Ports (abstract boundaries) the application layer depends on.

Each port is a ``typing.Protocol`` — structural typing, so an
infrastructure adapter satisfies a port simply by implementing its
methods, with no inheritance or registration required. This keeps
``app.infrastructure`` free to depend on ``app.application`` (to know
what shape to implement) without ``app.application`` ever importing
anything from ``app.infrastructure`` in return.
"""

from __future__ import annotations

from typing import Protocol

from app.design.models import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact
from app.domain.vision import ImageClassification

# `app.design.models` (the architecture/design bounded context) hasn't
# moved into `app.domain` yet — see README → "Clean Architecture
# Migration" → remaining slice "Move app/design/models.py into
# app/domain/". Importing it here is a deliberate, temporary compromise
# specific to that not-yet-done slice: `SystemDesignArtifact` is exactly
# as pure/I-O-free as anything already in `app.domain`, so it doesn't
# violate the Dependency Rule in spirit, only in current file location.


class RequirementsAgentPort(Protocol):
    """Turns free-text user input into a structured ``RequirementsArtifact``.

    Implemented by ``app.infrastructure.agents.requirements_agent
    .AgentFrameworkRequirementsAgent``, which is backed by Microsoft
    Agent Framework. The application layer (see
    ``app.application.use_cases.analyze_requirements``) depends only on
    this method signature — it has no idea Agent Framework, Azure
    OpenAI, or any particular model provider exists.
    """

    async def analyze(
        self,
        user_input: str,
        previous_artifact: RequirementsArtifact | None = None,
    ) -> RequirementsArtifact:
        """Analyze (or refine, if ``previous_artifact`` is given) requirements."""
        ...


class SystemDesignAgentPort(Protocol):
    """Turns requirements into a structured ``SystemDesignArtifact``.

    Implemented by ``app.infrastructure.agents.system_design_agent
    .AgentFrameworkSystemDesignAgent``, which is backed by Microsoft
    Agent Framework — the design-generation analogue of
    ``RequirementsAgentPort``. See
    ``app.application.use_cases.generate_system_design``.
    """

    async def generate(
        self,
        requirements: RequirementsArtifact,
        previous_design: SystemDesignArtifact | None = None,
        refinement_input: str | None = None,
    ) -> SystemDesignArtifact:
        """Generate (or refine, if ``previous_design`` is given) a design."""
        ...


class ImageClassifierPort(Protocol):
    """Classifies an uploaded image as a document screenshot or a system
    design/workflow diagram.

    Implemented by ``app.infrastructure.agents.image_classifier_agent
    .AgentFrameworkImageClassifierAgent``. See
    ``app.application.use_cases.classify_image`` and ``app/vision.py``'s
    module docstring for the wider document-vs-diagram story.
    """

    async def classify(self, content: bytes, filename: str) -> ImageClassification:
        """Classify ``content`` (an uploaded image's raw bytes)."""
        ...


class DiagramImageInterpreterPort(Protocol):
    """Derives a structured system design directly from a diagram image.

    Implemented by ``app.infrastructure.agents
    .diagram_image_interpreter_agent.AgentFrameworkDiagramImageInterpreterAgent``.
    See ``app.application.use_cases.interpret_diagram_image``.
    """

    async def interpret(
        self,
        content: bytes,
        filename: str,
        previous_design: SystemDesignArtifact | None = None,
        notes: str | None = None,
    ) -> SystemDesignArtifact:
        """Interpret (or refine, if ``previous_design`` is given) a
        diagram image's ``content`` (raw bytes) into a structured design."""
        ...
