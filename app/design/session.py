from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from ..models import RequirementsArtifact
from .analyzer import SystemDesignAnalyzer
from .diagram import ArchitectureDiagramGenerator
from .models import SystemDesignArtifact
from .validator import ArchitectureValidationError, ArchitectureValidator


class DesignGenerationWorkflowError(RuntimeError):
    """Raised when the architecture generation workflow fails."""


class DesignStore(Protocol):
    """Storage interface required by the design session."""

    def save_design_json(
        self,
        session_id: str,
        version: int,
        content: str,
    ) -> str:
        """Persist a system design JSON document."""
        ...

    def save_design_svg(
        self,
        session_id: str,
        version: int,
        content: str,
    ) -> str:
        """Persist an architecture diagram SVG document."""
        ...


class DesignSessionResult:
    """Result of generating an architecture."""

    design: SystemDesignArtifact
    design_blob: str
    diagram_blob: str
    version: int
    created_at: str

    def __init__(
        self,
        design: SystemDesignArtifact,
        design_blob: str,
        diagram_blob: str,
        version: int,
    ) -> None:
        self.design = design
        self.design_blob = design_blob
        self.diagram_blob = diagram_blob
        self.version = version
        self.created_at = datetime.now(UTC).isoformat()


class ArchitectureSession:
    """Orchestrate architecture generation, validation, and persistence."""

    def __init__(
        self,
        analyzer: SystemDesignAnalyzer,
        diagram_generator: ArchitectureDiagramGenerator,
        validator: ArchitectureValidator,
        store: DesignStore,
        session_id: str,
        version: int = 0,
    ) -> None:
        self.analyzer = analyzer
        self.diagram_generator = diagram_generator
        self.validator = validator
        self.store = store
        self.session_id = session_id
        # Starts at 0 for a brand-new architecture (the first `generate()`
        # call produces v1). Callers refining an already-accepted
        # architecture pass in the session's current `design_version` here,
        # so a refinement continues the same version sequence instead of
        # restarting it at v1 — see `refine_architecture` in
        # app/api/routes/requirements.py.
        self.version = version

    def generate(
        self,
        requirements: RequirementsArtifact,
        previous_design: SystemDesignArtifact | None = None,
        refinement_input: str | None = None,
    ) -> DesignSessionResult:
        """Generate, validate, render, and persist an architecture.

        Passing ``previous_design``/``refinement_input`` refines that design
        in place instead of generating a fresh one — see
        ``SystemDesignAnalyzer.analyze``.
        """

        next_version = self.version + 1

        try:
            design: SystemDesignArtifact = self.analyzer.analyze(
                requirements,
                previous_design=previous_design,
                refinement_input=refinement_input,
            )

            validated_design: SystemDesignArtifact = self.validator.validate(design)

            svg = self.diagram_generator.generate(validated_design)

            design_json = validated_design.model_dump_json(indent=2)

            design_blob = self.store.save_design_json(
                session_id=self.session_id,
                version=next_version,
                content=design_json,
            )

            diagram_blob = self.store.save_design_svg(
                session_id=self.session_id,
                version=next_version,
                content=svg,
            )

        except ArchitectureValidationError as exc:
            raise DesignGenerationWorkflowError(
                f"Architecture validation failed: {exc}"
            ) from exc

        except Exception as exc:
            raise DesignGenerationWorkflowError(
                f"Architecture generation failed: {exc}"
            ) from exc

        # Only consume the version after the complete workflow succeeds.
        self.version = next_version

        return DesignSessionResult(
            design=validated_design,
            design_blob=design_blob,
            diagram_blob=diagram_blob,
            version=next_version,
        )
