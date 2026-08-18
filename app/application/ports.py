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

from app.domain.design import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact, StoredArtifact
from app.domain.session import SessionRecord
from app.domain.vision import ImageClassification


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
    ``app.application.use_cases.classify_image``'s module docstring for
    the wider document-vs-diagram story this exists to support.
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


class ArtifactStorePort(Protocol):
    """Persists/retrieves versioned requirements and design artifacts.

    Implemented by ``app.infrastructure.artifact_store.ArtifactStore``,
    backed by Azure Blob Storage. Every method here is synchronous —
    unlike the agent ports above, nothing in this project's call sites
    (the CLI, the sync FastAPI routes, the MCP server) needs an async
    storage call badly enough to justify every implementation paying for
    it, and Blob Storage's SDK is used synchronously throughout this
    project for exactly that reason (see
    ``app.infrastructure.session_store``'s module docstring for the
    parallel reasoning on the Cosmos side).
    """

    def save(self, artifact: StoredArtifact) -> str:
        """Save a requirements artifact version. Returns its blob name."""
        ...

    def list_requirements_versions(self, session_id: str) -> list[int]:
        """Every requirements version persisted for this session, oldest first."""
        ...

    def get_requirements_json(self, session_id: str, version: int) -> str | None:
        """The raw ``StoredArtifact`` JSON for one requirements version, or
        ``None`` if that version was never persisted."""
        ...

    def list_design_versions(self, session_id: str) -> list[int]:
        """Every design version persisted for this session, oldest first."""
        ...

    def get_latest_design_version(self, session_id: str) -> int:
        """The latest persisted design JSON version for a session, or ``0``."""
        ...

    def get_design_json(self, session_id: str, version: int) -> str | None:
        """The raw ``SystemDesignArtifact`` JSON for one design version, or
        ``None`` if it was never persisted."""
        ...

    def get_design_svg(self, session_id: str, version: int) -> str | None:
        """The raw architecture diagram SVG markup for one design version,
        or ``None`` if it was never persisted."""
        ...

    def save_design_json(self, session_id: str, version: int, content: str) -> str:
        """Create a design JSON version without overwriting it.

        Raises ``app.application.errors.ArtifactVersionConflict`` if
        ``version`` already exists for this session.
        """
        ...

    def save_design_svg(self, session_id: str, version: int, content: str) -> str:
        """Create the SVG for an existing design version."""
        ...

    def delete_design_json(self, session_id: str, version: int) -> None:
        """Delete a design JSON artifact if it exists."""
        ...

    def delete_design_svg(self, session_id: str, version: int) -> None:
        """Delete a design SVG artifact if it exists."""
        ...

    def save_source_file(
        self, session_id: str, version: int, filename: str, content: bytes
    ) -> str:
        """Persist the original uploaded requirements source document."""
        ...

    def get_source_file(
        self, session_id: str, version: int
    ) -> tuple[bytes, str] | None:
        """The original uploaded file for a requirements version — returns
        ``(content_bytes, content_type)``, or ``None`` if that version
        wasn't created from an uploaded file."""
        ...

    def close(self) -> None:
        """Release any underlying network resources. Called once, at
        shutdown, by long-running callers (the web API's ``lifespan``)."""
        ...


class SessionStorePort(Protocol):
    """Persists/retrieves a requirements-to-architecture run's state.

    Implemented by
    ``app.infrastructure.session_store.CosmosSessionStore``, backed by
    Cosmos DB. Synchronous for the same reason ``ArtifactStorePort`` is —
    see its docstring.
    """

    def create(self, record: SessionRecord) -> SessionRecord: ...

    def get(self, session_id: str) -> SessionRecord | None: ...

    def upsert(self, record: SessionRecord) -> SessionRecord:
        """Persist ``record``, raising
        ``app.application.errors.SessionConflictError`` instead of
        silently overwriting a concurrent writer's change when ``record``
        carries a stale concurrency token."""
        ...

    def list_for_owner(self, owner_oid: str) -> list[SessionRecord]:
        """Every session started by one user, newest first."""
        ...

    def list_all(self) -> list[SessionRecord]:
        """Every session across every owner, newest first — for
        Admin-role callers only (see ``app.api.ownership``)."""
        ...


class DiagramRendererPort(Protocol):
    """Renders a structured design into a displayable architecture diagram.

    Implemented by ``app.design.diagram.ArchitectureDiagramGenerator``,
    backed by Graphviz. Unlike the agent ports above, this isn't wired
    through ``app.infrastructure.composition`` — rendering needs no
    credentials or environment configuration, so callers
    (``app.design.session.ArchitectureSession``, ``app/main.py``,
    ``app/api/dependencies.py``, ``app/mcp/server.py``) construct
    ``ArchitectureDiagramGenerator()`` directly. The point of this port
    isn't to hide *how* it's built — it's so ``ArchitectureSession`` (and
    anything else that renders a design) depends on "something that can
    render a design", not on Graphviz specifically.
    """

    def generate(self, design: SystemDesignArtifact) -> str:
        """Render ``design`` as an SVG diagram.

        Raises ``app.application.errors.DiagramGenerationError`` if
        rendering fails.
        """
        ...
