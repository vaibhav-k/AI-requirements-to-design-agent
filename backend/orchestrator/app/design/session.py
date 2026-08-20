from __future__ import annotations

from datetime import UTC, datetime

from app.application.errors import ArchitectureValidationError
from app.application.ports import (
    ArchitectureValidatorPort,
    ArtifactStorePort,
    DiagramRendererPort,
)
from app.application.use_cases.generate_system_design import (
    GenerateSystemDesignUseCase,
)
from app.domain.design import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact
from app.infrastructure.sync_bridge import run_sync


class DesignGenerationWorkflowError(RuntimeError):
    """Raised when the architecture generation workflow fails."""


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
        analyzer: GenerateSystemDesignUseCase,
        diagram_generator: DiagramRendererPort,
        validator: ArchitectureValidatorPort,
        store: ArtifactStorePort,
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
        # restarting it at v1 - see `refine_architecture` in
        # app/api/routes/requirements.py.
        self.version = version

    def generate(
        self,
        requirements: RequirementsArtifact,
        previous_design: SystemDesignArtifact | None = None,
        refinement_input: str | None = None,
    ) -> DesignSessionResult:
        """Generate, validate, render, and persist an architecture from
        requirements text.

        Passing ``previous_design``/``refinement_input`` refines that design
        in place instead of generating a fresh one - see
        ``GenerateSystemDesignUseCase.execute``. The validate/render/persist
        tail of this is shared with :meth:`generate_from_design` (see there
        for the image-diagram entry point that skips straight past this
        text-based analysis step).

        Synchronous on purpose - the CLI (``app/main.py``) and the sync
        FastAPI routes that construct this session call it directly with
        no event loop of their own; ``run_sync`` (see
        ``app/infrastructure/sync_bridge.py``) bridges into
        ``self.analyzer.execute``'s async call, the same guard the former
        ``SystemDesignAnalyzer.analyze`` facade used to provide.
        """

        try:
            design: SystemDesignArtifact = run_sync(
                self.analyzer.execute(
                    requirements,
                    previous_design=previous_design,
                    refinement_input=refinement_input,
                ),
                caller="ArchitectureSession.generate",
            )
        except Exception as exc:
            raise DesignGenerationWorkflowError(
                f"Architecture generation failed: {exc}"
            ) from exc

        return self.generate_from_design(design)

    def generate_from_design(self, design: SystemDesignArtifact) -> DesignSessionResult:
        """Validate, render, and persist an already-produced design.

        This is :meth:`generate`'s tail end, factored out so a design that
        didn't come from :attr:`analyzer` - today, one interpreted directly
        from an uploaded diagram image by
        ``app/vision.py``'s ``DiagramImageInterpreter`` (see the upload
        routes in ``app/api/routes/requirements.py``) - goes through the
        exact same validation, diagram rendering, and Blob persistence as a
        text-derived one, rather than a parallel, easily-divergent copy of
        that logic.
        """

        next_version = self.version + 1

        try:
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
