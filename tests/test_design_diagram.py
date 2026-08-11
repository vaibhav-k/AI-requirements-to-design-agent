from app.design.diagram import ArchitectureDiagramGenerator
from app.design.models import (
    DesignComponent,
    DesignInterface,
    ExternalDependency,
    SystemDesignArtifact,
)


def test_diagram_contains_components() -> None:
    design = SystemDesignArtifact(
        architecture_summary="Document platform.",
        components=[
            DesignComponent(
                id="api",
                name="API",
                responsibility="Handles requests.",
            ),
            DesignComponent(
                id="service",
                name="Document Service",
                responsibility="Processes documents.",
            ),
        ],
        interfaces=[
            DesignInterface(
                id="api-service",
                name="Document Request",
                purpose="Sends requests.",
                source_component="api",
                target_component="service",
            )
        ],
    )

    svg = ArchitectureDiagramGenerator().generate(design)

    assert "<svg" in svg
    assert "API" in svg
    assert "Document Service" in svg


def test_diagram_contains_external_dependency() -> None:
    design = SystemDesignArtifact(
        architecture_summary="Document platform.",
        components=[
            DesignComponent(
                id="service",
                name="Document Service",
                responsibility="Processes documents.",
            )
        ],
        external_dependencies=[
            ExternalDependency(
                id="blob",
                name="Blob Storage",
                purpose="Stores documents.",
                used_by_components=["service"],
            )
        ],
    )

    svg = ArchitectureDiagramGenerator().generate(design)

    assert "<svg" in svg
    assert "Blob Storage" in svg
    assert "Document Service" in svg
