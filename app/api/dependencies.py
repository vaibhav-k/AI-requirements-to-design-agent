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

from fastapi import Request

from app.analyzer import RequirementsAnalyzer
from app.design.analyzer import SystemDesignAnalyzer
from app.design.diagram import ArchitectureDiagramGenerator
from app.design.validator import ArchitectureValidator
from app.infrastructure.session_store import SessionStore
from app.storage import ArtifactStore


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
