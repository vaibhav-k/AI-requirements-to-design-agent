"""Ports (abstract boundaries) the application layer depends on.

Each port is a ``typing.Protocol`` - structural typing, so an
infrastructure adapter satisfies a port simply by implementing its
methods, with no inheritance or registration required. This keeps
``app.infrastructure`` free to depend on ``app.application`` (to know
what shape to implement) without ``app.application`` ever importing
anything from ``app.infrastructure`` in return.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.design import ArchitectureDiagrams, SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact, StoredArtifact
from app.domain.session import SessionRecord
from app.domain.technical_design import TechnicalDesignArtifact, TechnicalDesignExport
from app.domain.vision import ImageClassification
from app.domain.work_breakdown import WorkBreakdownArtifact, WorkBreakdownExport


class RequirementsAgentPort(Protocol):
    """Turns free-text user input into a structured ``RequirementsArtifact``.

    Implemented by ``app.infrastructure.agents.requirements_agent
    .AgentFrameworkRequirementsAgent``, which is backed by Microsoft
    Agent Framework. The application layer (see
    ``app.application.use_cases.analyze_requirements``) depends only on
    this method signature - it has no idea Agent Framework, Azure
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
    Agent Framework - the design-generation analogue of
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
    backed by Azure Blob Storage. Every method here is synchronous -
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

    def get_design_svg(
        self, session_id: str, version: int, kind: str = "logical"
    ) -> str | None:
        """The raw architecture diagram SVG markup for one design
        version, or ``None`` if it was never persisted.

        ``kind`` is ``"logical"`` (the Logical Architecture Diagram -
        the default, matching every design version persisted before the
        two-diagram architecture-generation phase existed) or
        ``"azure"`` (the Azure Service Mapping Diagram).
        """
        ...

    def save_design_json(self, session_id: str, version: int, content: str) -> str:
        """Create a design JSON version without overwriting it.

        Raises ``app.application.errors.ArtifactVersionConflict`` if
        ``version`` already exists for this session.
        """
        ...

    def save_design_svg(
        self, session_id: str, version: int, content: str, kind: str = "logical"
    ) -> str:
        """Create one of the two SVG diagrams for an existing design
        version - see ``get_design_svg`` for ``kind``."""
        ...

    def delete_design_json(self, session_id: str, version: int) -> None:
        """Delete a design JSON artifact if it exists."""
        ...

    def delete_design_svg(
        self, session_id: str, version: int, kind: str = "logical"
    ) -> None:
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
        """The original uploaded file for a requirements version - returns
        ``(content_bytes, content_type)``, or ``None`` if that version
        wasn't created from an uploaded file."""
        ...

    def list_work_breakdown_versions(self, session_id: str) -> list[int]:
        """Every work breakdown version persisted for this session, oldest
        first - the work-breakdown analogue of ``list_design_versions``."""
        ...

    def get_work_breakdown_json(self, session_id: str, version: int) -> str | None:
        """The raw ``WorkBreakdownArtifact`` JSON for one version, or
        ``None`` if it was never persisted."""
        ...

    def save_work_breakdown_json(
        self, session_id: str, version: int, content: str
    ) -> str:
        """Create a work breakdown JSON version without overwriting it.

        Raises ``app.application.errors.ArtifactVersionConflict`` if
        ``version`` already exists for this session - same immutable-once-
        written contract as ``save_design_json``.
        """
        ...

    def get_work_breakdown_csv(self, session_id: str, version: int) -> str | None:
        """The most recently rendered CSV export for one work breakdown
        version, or ``None`` if it was never exported."""
        ...

    def save_work_breakdown_csv(
        self, session_id: str, version: int, content: str
    ) -> str:
        """Persist (overwriting any previous export) the rendered CSV for
        one work breakdown version.

        Unlike ``save_work_breakdown_json``, this overwrites - the CSV is a
        derived, re-computable artifact of an already-persisted version,
        not itself a new version, so exporting the same version twice must
        not conflict.
        """
        ...

    def list_technical_design_versions(self, session_id: str) -> list[int]:
        """Every technical design version persisted for this session,
        oldest first - the technical-design analogue of
        ``list_work_breakdown_versions``."""
        ...

    def get_technical_design_json(self, session_id: str, version: int) -> str | None:
        """The raw ``TechnicalDesignArtifact`` JSON for one version, or
        ``None`` if it was never persisted."""
        ...

    def save_technical_design_json(
        self, session_id: str, version: int, content: str
    ) -> str:
        """Create a technical design JSON version without overwriting it.

        Raises ``app.application.errors.ArtifactVersionConflict`` if
        ``version`` already exists for this session - same immutable-once-
        written contract as ``save_work_breakdown_json``.
        """
        ...

    def get_technical_design_docx(self, session_id: str, version: int) -> bytes | None:
        """The most recently rendered ``.docx`` export for one technical
        design version, or ``None`` if it was never exported."""
        ...

    def save_technical_design_docx(
        self, session_id: str, version: int, content: bytes
    ) -> str:
        """Persist (overwriting any previous export) the rendered
        ``.docx`` for one technical design version.

        Same "derived, re-computable artifact, overwrite rather than
        conflict" rule as ``save_work_breakdown_csv``.
        """
        ...

    def close(self) -> None:
        """Release any underlying network resources. Called once, at
        shutdown, by long-running callers (the web API's ``lifespan``)."""
        ...


class SessionStorePort(Protocol):
    """Persists/retrieves a requirements-to-architecture run's state.

    Implemented by
    ``app.infrastructure.session_store.CosmosSessionStore``, backed by
    Cosmos DB. Synchronous for the same reason ``ArtifactStorePort`` is -
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
        """Every session across every owner, newest first - for
        Admin-role callers only (see ``app.api.ownership``)."""
        ...


class DiagramRendererPort(Protocol):
    """Renders a structured design into a displayable architecture diagram.

    Implemented by ``app.infrastructure.tools_client.McpToolsClient``,
    which reaches the deterministic, Graphviz-backed renderer that used to
    live in-process (``app.design.diagram.ArchitectureDiagramGenerator``)
    over MCP instead - see README -> "Service Architecture" for the full
    orchestrator -> mcp-wrapper -> tools-service call path. Wired through
    ``app.infrastructure.composition`` like the agent ports above (unlike
    before the split, this now needs the tools-service's MCP endpoint URL,
    so it's no longer credential-free enough to construct directly at
    every call site).
    """

    def generate(
        self,
        design: SystemDesignArtifact,
        version: int,
        generated_at: str,
    ) -> ArchitectureDiagrams:
        """Render ``design`` as both required architecture diagrams (the
        Logical Architecture Diagram and the Azure Service Mapping
        Diagram).

        ``version``/``generated_at`` are stamped into each diagram's
        deterministic metadata block (never invented) - the design
        version this render corresponds to, and an ISO timestamp of when
        it was generated.

        Raises ``app.application.errors.DiagramGenerationError`` if
        rendering fails.
        """
        ...


class ArchitectureValidatorPort(Protocol):
    """Validates the semantic integrity of a structured design.

    Implemented by ``app.infrastructure.tools_client.McpToolsClient`` -
    the validation analogue of ``DiagramRendererPort`` above, reaching the
    deterministic validator that used to live in-process
    (``app.design.validator.ArchitectureValidator``) over the same MCP
    path instead. See README -> "Service Architecture".
    """

    def validate(self, design: SystemDesignArtifact) -> SystemDesignArtifact:
        """Validate and return ``design``.

        Raises ``app.application.errors.ArchitectureValidationError`` if
        validation fails.
        """
        ...


class WorkBreakdownAgentPort(Protocol):
    """Turns requirements + architecture into a structured
    ``WorkBreakdownArtifact`` (Feature -> Story -> Task).

    Implemented by ``app.infrastructure.agents.work_breakdown_agent
    .AgentFrameworkWorkBreakdownAgent``, which is backed by Microsoft
    Agent Framework - the work-breakdown analogue of
    ``SystemDesignAgentPort``. See
    ``app.application.use_cases.generate_work_breakdown``.
    """

    async def generate(
        self,
        requirements: RequirementsArtifact,
        design: SystemDesignArtifact,
        previous_breakdown: WorkBreakdownArtifact | None = None,
        refinement_input: str | None = None,
    ) -> WorkBreakdownArtifact:
        """Generate (or refine, if ``previous_breakdown`` is given) a work breakdown."""
        ...


class WorkBreakdownExporterPort(Protocol):
    """Renders a structured work breakdown into an import-ready CSV, with
    traceability validation against the requirements/architecture it was
    generated from.

    Implemented by ``app.infrastructure.tools_client.McpToolsClient`` -
    the work-breakdown analogue of ``DiagramRendererPort``/
    ``ArchitectureValidatorPort`` above, reaching the deterministic
    exporter that lives in ``backend/tools-service`` (never in-process
    here) over the same design-tools MCP path. See README -> "Service
    Architecture".
    """

    def export(
        self,
        breakdown: WorkBreakdownArtifact,
        requirements: RequirementsArtifact,
        design: SystemDesignArtifact,
    ) -> WorkBreakdownExport:
        """Validate ``breakdown`` against ``requirements``/``design`` and
        render it to CSV.

        Raises ``app.application.errors.WorkBreakdownExportError`` if the
        tools-service call fails.
        """
        ...


class TechnicalWriterAgentPort(Protocol):
    """Turns requirements + architecture + work breakdown into a
    structured ``TechnicalDesignArtifact``.

    Implemented by ``app.infrastructure.agents.technical_writer_agent
    .AgentFrameworkTechnicalWriterAgent``, which is backed by Microsoft
    Agent Framework - the technical-design analogue of
    ``WorkBreakdownAgentPort``. See
    ``app.application.use_cases.generate_technical_design``.
    """

    async def generate(
        self,
        requirements: RequirementsArtifact,
        design: SystemDesignArtifact,
        work_breakdown: WorkBreakdownArtifact,
        previous_document: TechnicalDesignArtifact | None = None,
        refinement_input: str | None = None,
    ) -> TechnicalDesignArtifact:
        """Generate (or refine, if ``previous_document`` is given) a
        technical design document."""
        ...


class DocumentExporterPort(Protocol):
    """Renders a structured technical design document into a downloadable
    ``.docx`` file, with the approved architecture diagram embedded.

    Implemented by ``app.infrastructure.tools_client.McpToolsClient`` -
    the technical-design analogue of ``WorkBreakdownExporterPort`` above,
    reaching the deterministic, python-docx-backed renderer that lives in
    ``backend/tools-service`` over the same design-tools MCP path. See
    README -> "Service Architecture".
    """

    def export_document(
        self,
        document: TechnicalDesignArtifact,
        design: SystemDesignArtifact,
        requirements: RequirementsArtifact,
        work_breakdown: WorkBreakdownArtifact,
    ) -> TechnicalDesignExport:
        """Render ``document`` to ``.docx``, embedding the diagram
        rendered from ``design``.

        Named ``export_document`` rather than ``export`` only because
        ``McpToolsClient`` implements both this port and
        ``WorkBreakdownExporterPort`` (whose method is already named
        ``export``) on the same class - a plain naming collision, not a
        semantic difference from ``WorkBreakdownExporterPort.export``.

        Raises ``app.application.errors.TechnicalDesignExportError`` if
        the tools-service call fails.
        """
        ...
