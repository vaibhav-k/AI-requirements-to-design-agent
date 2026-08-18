"""FastAPI dependency-injection functions for the requirements/design routes.

Deliberately plain functions rather than ``lru_cache``d singletons: routes
depend on ``get_session_store``/``get_artifact_store``/etc. by reference, and
tests replace them wholesale with ``app.dependency_overrides[fn] = lambda:
fake`` — so a real Cosmos or Blob Storage client (or a real Azure OpenAI key)
is never required to exercise route logic. The ``/health`` and ``/me``
endpoints in ``app/web/main.py`` don't need this because they don't touch
any external service; every route added here does, so it gets the same
override-friendly treatment as the rest of the route dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request

from app.analyzer import RequirementsAnalyzer
from app.design.analyzer import SystemDesignAnalyzer
from app.design.diagram import ArchitectureDiagramGenerator
from app.design.validator import ArchitectureValidator
from app.infrastructure.session_store import SessionStore
from app.ingestion import RequirementsDocumentExtractor
from app.storage import ArtifactStore
from app.vision import DiagramImageInterpreter, ImageInputClassifier


def get_session_store(request: Request) -> SessionStore:
    store: SessionStore = request.app.state.session_store
    return store


def get_artifact_store(request: Request) -> ArtifactStore:
    store: ArtifactStore = request.app.state.artifact_store
    return store


def get_requirements_analyzer() -> RequirementsAnalyzer:
    return RequirementsAnalyzer()


def get_design_analyzer() -> SystemDesignAnalyzer:
    return SystemDesignAnalyzer()


def get_diagram_generator() -> ArchitectureDiagramGenerator:
    return ArchitectureDiagramGenerator()


def get_validator() -> ArchitectureValidator:
    return ArchitectureValidator()


def get_document_extractor() -> RequirementsDocumentExtractor:
    return RequirementsDocumentExtractor()


def get_image_classifier() -> ImageInputClassifier:
    return ImageInputClassifier()


def get_diagram_interpreter() -> DiagramImageInterpreter:
    return DiagramImageInterpreter()


@dataclass
class ArchitectureGenerationDependencies:
    """Bundles the services an architecture-generation route needs.

    ``accept_run`` and ``refine_architecture`` (``app/api/routes/requirements.py``)
    each construct an ``ArchitectureSession`` from the same four services.
    Requiring all four as separate ``Depends(...)`` parameters, alongside
    ``session_id``/``request``/``store``, pushed those routes' own parameter
    counts past a reasonable threshold. Bundling them here keeps each
    individual service overridable in tests exactly as before — FastAPI
    resolves ``get_artifact_store``/``get_design_analyzer``/etc. (and thus
    any ``app.dependency_overrides`` entry for one of them) before this
    factory runs, so nothing about the existing override-per-service test
    pattern changes.
    """

    store: ArtifactStore
    analyzer: SystemDesignAnalyzer
    diagram_generator: ArchitectureDiagramGenerator
    validator: ArchitectureValidator


def get_architecture_generation_dependencies(
    artifact_store: ArtifactStore = Depends(get_artifact_store),  # noqa: B008
    analyzer: SystemDesignAnalyzer = Depends(get_design_analyzer),  # noqa: B008
    diagram_generator: ArchitectureDiagramGenerator = Depends(  # noqa: B008
        get_diagram_generator
    ),
    validator: ArchitectureValidator = Depends(get_validator),  # noqa: B008
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
    file, analyze it, and persist the result — the same three services,
    each duplicated as a separate parameter on both routes. See
    ``ArchitectureGenerationDependencies`` above for why bundling these
    doesn't change the individual-service test-override pattern.
    """

    artifact_store: ArtifactStore
    analyzer: RequirementsAnalyzer
    extractor: RequirementsDocumentExtractor


def get_requirements_upload_dependencies(
    artifact_store: ArtifactStore = Depends(get_artifact_store),  # noqa: B008
    analyzer: RequirementsAnalyzer = Depends(get_requirements_analyzer),  # noqa: B008
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
    before) or a system design/workflow diagram — see ``app/vision.py``.
    The diagram branch needs everything ``ArchitectureGenerationDependencies``
    already bundles (to validate, render, and persist the interpreted
    design through ``ArchitectureSession.generate_from_design``) plus the
    classifier and interpreter themselves, so this composes both rather
    than repeating either.
    """

    artifact_store: ArtifactStore
    classifier: ImageInputClassifier
    diagram_interpreter: DiagramImageInterpreter
    design_analyzer: SystemDesignAnalyzer
    diagram_generator: ArchitectureDiagramGenerator
    validator: ArchitectureValidator


def get_image_upload_dependencies(
    artifact_store: ArtifactStore = Depends(get_artifact_store),  # noqa: B008
    classifier: ImageInputClassifier = Depends(get_image_classifier),  # noqa: B008
    diagram_interpreter: DiagramImageInterpreter = Depends(  # noqa: B008
        get_diagram_interpreter
    ),
    design_analyzer: SystemDesignAnalyzer = Depends(get_design_analyzer),  # noqa: B008
    diagram_generator: ArchitectureDiagramGenerator = Depends(  # noqa: B008
        get_diagram_generator
    ),
    validator: ArchitectureValidator = Depends(get_validator),  # noqa: B008
) -> ImageUploadDependencies:
    return ImageUploadDependencies(
        artifact_store=artifact_store,
        classifier=classifier,
        diagram_interpreter=diagram_interpreter,
        design_analyzer=design_analyzer,
        diagram_generator=diagram_generator,
        validator=validator,
    )
