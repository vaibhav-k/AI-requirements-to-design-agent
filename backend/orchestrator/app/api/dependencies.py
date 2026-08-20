"""FastAPI dependency-injection functions for the requirements/design routes.

Deliberately plain functions rather than ``lru_cache``d singletons: routes
depend on ``get_session_store``/``get_artifact_store``/etc. by reference, and
tests replace them wholesale with ``app.dependency_overrides[fn] = lambda:
fake`` - so a real Cosmos or Blob Storage client (or a real Azure OpenAI key)
is never required to exercise route logic. The ``/health`` and ``/me``
endpoints in ``app/web/main.py`` don't need this because they don't touch
any external service; every route added here does, so it gets the same
override-friendly treatment as the rest of the route dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request

from app.application.ports import (
    ArchitectureValidatorPort,
    ArtifactStorePort,
    DiagramRendererPort,
    SessionStorePort,
    WorkBreakdownExporterPort,
)
from app.application.use_cases.analyze_requirements import AnalyzeRequirementsUseCase
from app.application.use_cases.classify_image import ClassifyImageUseCase
from app.application.use_cases.generate_session_work_breakdown import (
    ExportSessionWorkBreakdownUseCase,
    GenerateSessionWorkBreakdownUseCase,
)
from app.application.use_cases.generate_system_design import (
    GenerateSystemDesignUseCase,
)
from app.application.use_cases.generate_work_breakdown import (
    GenerateWorkBreakdownUseCase,
)
from app.application.use_cases.interpret_diagram_image import (
    InterpretDiagramImageUseCase,
)
from app.infrastructure.composition import (
    build_design_tools_client,
    build_diagram_interpreter_use_case,
    build_image_classifier_use_case,
    build_requirements_use_case,
    build_system_design_use_case,
    build_work_breakdown_use_case,
)
from app.ingestion import RequirementsDocumentExtractor


def get_session_store(request: Request) -> SessionStorePort:
    store: SessionStorePort = request.app.state.session_store
    return store


def get_artifact_store(request: Request) -> ArtifactStorePort:
    store: ArtifactStorePort = request.app.state.artifact_store
    return store


def get_requirements_analyzer() -> AnalyzeRequirementsUseCase:
    return build_requirements_use_case()


def get_design_analyzer() -> GenerateSystemDesignUseCase:
    return build_system_design_use_case()


def get_diagram_generator() -> DiagramRendererPort:
    return build_design_tools_client()


def get_validator() -> ArchitectureValidatorPort:
    return build_design_tools_client()


def get_document_extractor() -> RequirementsDocumentExtractor:
    return RequirementsDocumentExtractor()


def get_image_classifier() -> ClassifyImageUseCase:
    return build_image_classifier_use_case()


def get_diagram_interpreter() -> InterpretDiagramImageUseCase:
    return build_diagram_interpreter_use_case()


def get_work_breakdown_analyzer() -> GenerateWorkBreakdownUseCase:
    return build_work_breakdown_use_case()


def get_work_breakdown_exporter() -> WorkBreakdownExporterPort:
    return build_design_tools_client()


@dataclass
class ArchitectureGenerationDependencies:
    """Bundles the services an architecture-generation route needs.

    ``accept_run`` and ``refine_architecture`` (``app/api/routes/requirements.py``)
    each construct an ``ArchitectureSession`` from the same four services.
    Requiring all four as separate ``Depends(...)`` parameters, alongside
    ``session_id``/``request``/``store``, pushed those routes' own parameter
    counts past a reasonable threshold. Bundling them here keeps each
    individual service overridable in tests exactly as before - FastAPI
    resolves ``get_artifact_store``/``get_design_analyzer``/etc. (and thus
    any ``app.dependency_overrides`` entry for one of them) before this
    factory runs, so nothing about the existing override-per-service test
    pattern changes.
    """

    store: ArtifactStorePort
    analyzer: GenerateSystemDesignUseCase
    diagram_generator: DiagramRendererPort
    validator: ArchitectureValidatorPort


def get_architecture_generation_dependencies(
    artifact_store: ArtifactStorePort = Depends(get_artifact_store),  # noqa: B008
    analyzer: GenerateSystemDesignUseCase = Depends(get_design_analyzer),  # noqa: B008
    diagram_generator: DiagramRendererPort = Depends(  # noqa: B008
        get_diagram_generator
    ),
    validator: ArchitectureValidatorPort = Depends(get_validator),  # noqa: B008
) -> ArchitectureGenerationDependencies:
    return ArchitectureGenerationDependencies(
        store=artifact_store,
        analyzer=analyzer,
        diagram_generator=diagram_generator,
        validator=validator,
    )


@dataclass
class RequirementsUploadDependencies:
    """Bundles the services a document-upload requirements route needs.

    ``start_run_from_upload`` and ``refine_run_from_upload``
    (``app/api/routes/requirements.py``) both extract text from an uploaded
    file, analyze it, and persist the result - the same three services,
    each duplicated as a separate parameter on both routes. See
    ``ArchitectureGenerationDependencies`` above for why bundling these
    doesn't change the individual-service test-override pattern.
    """

    artifact_store: ArtifactStorePort
    analyzer: AnalyzeRequirementsUseCase
    extractor: RequirementsDocumentExtractor


def get_requirements_upload_dependencies(
    artifact_store: ArtifactStorePort = Depends(get_artifact_store),  # noqa: B008
    analyzer: AnalyzeRequirementsUseCase = Depends(  # noqa: B008
        get_requirements_analyzer
    ),
    extractor: RequirementsDocumentExtractor = Depends(  # noqa: B008
        get_document_extractor
    ),
) -> RequirementsUploadDependencies:
    return RequirementsUploadDependencies(
        artifact_store=artifact_store,
        analyzer=analyzer,
        extractor=extractor,
    )


@dataclass
class ImageUploadDependencies:
    """Bundles the services image-input classification needs on top of
    :class:`RequirementsUploadDependencies`.

    An uploaded PNG/JPG/JPEG could turn out to be either a document
    screenshot (handled by ``RequirementsUploadDependencies`` exactly as
    before) or a system design/workflow diagram - see
    ``app.application.use_cases.classify_image``. The diagram branch
    needs everything ``ArchitectureGenerationDependencies``
    already bundles (to validate, render, and persist the interpreted
    design through ``ArchitectureSession.generate_from_design``) plus the
    classifier and interpreter themselves, so this composes both rather
    than repeating either.
    """

    artifact_store: ArtifactStorePort
    classifier: ClassifyImageUseCase
    diagram_interpreter: InterpretDiagramImageUseCase
    design_analyzer: GenerateSystemDesignUseCase
    diagram_generator: DiagramRendererPort
    validator: ArchitectureValidatorPort


def get_image_upload_dependencies(
    artifact_store: ArtifactStorePort = Depends(get_artifact_store),  # noqa: B008
    classifier: ClassifyImageUseCase = Depends(get_image_classifier),  # noqa: B008
    diagram_interpreter: InterpretDiagramImageUseCase = Depends(  # noqa: B008
        get_diagram_interpreter
    ),
    design_analyzer: GenerateSystemDesignUseCase = Depends(  # noqa: B008
        get_design_analyzer
    ),
    diagram_generator: DiagramRendererPort = Depends(  # noqa: B008
        get_diagram_generator
    ),
    validator: ArchitectureValidatorPort = Depends(get_validator),  # noqa: B008
) -> ImageUploadDependencies:
    return ImageUploadDependencies(
        artifact_store=artifact_store,
        classifier=classifier,
        diagram_interpreter=diagram_interpreter,
        design_analyzer=design_analyzer,
        diagram_generator=diagram_generator,
        validator=validator,
    )


@dataclass
class WorkBreakdownGenerationDependencies:
    """Bundles the services ``generate_work_breakdown``/``refine_work_breakdown``
    (``app/api/routes/work_breakdown.py``) need - the work-breakdown analogue
    of ``ArchitectureGenerationDependencies``.
    """

    session_use_case: GenerateSessionWorkBreakdownUseCase


def get_work_breakdown_generation_dependencies(
    artifact_store: ArtifactStorePort = Depends(get_artifact_store),  # noqa: B008
    analyzer: GenerateWorkBreakdownUseCase = Depends(  # noqa: B008
        get_work_breakdown_analyzer
    ),
) -> WorkBreakdownGenerationDependencies:
    return WorkBreakdownGenerationDependencies(
        session_use_case=GenerateSessionWorkBreakdownUseCase(
            generator=analyzer, artifact_store=artifact_store
        )
    )


@dataclass
class WorkBreakdownExportDependencies:
    """Bundles the services ``export_work_breakdown``
    (``app/api/routes/work_breakdown.py``) needs."""

    session_use_case: ExportSessionWorkBreakdownUseCase


def get_work_breakdown_export_dependencies(
    artifact_store: ArtifactStorePort = Depends(get_artifact_store),  # noqa: B008
    exporter: WorkBreakdownExporterPort = Depends(  # noqa: B008
        get_work_breakdown_exporter
    ),
) -> WorkBreakdownExportDependencies:
    return WorkBreakdownExportDependencies(
        session_use_case=ExportSessionWorkBreakdownUseCase(
            exporter=exporter, artifact_store=artifact_store
        )
    )
