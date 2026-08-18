import pytest

from app.design.validator import (
    ArchitectureValidationError,
    ArchitectureValidator,
)
from app.domain.design import (
    DesignComponent,
    DesignInterface,
    ExternalDependency,
    SystemDesignArtifact,
)


def test_valid_architecture_passes() -> None:
    design = SystemDesignArtifact(
        architecture_summary="Valid architecture.",
        components=[
            DesignComponent(
                id="api",
                name="API",
                responsibility="Handles requests.",
                requirement_ids=["FR-001"],
            ),
            DesignComponent(
                id="service",
                name="Service",
                responsibility="Processes requests.",
                requirement_ids=["FR-001"],
            ),
        ],
        interfaces=[
            DesignInterface(
                id="api-service",
                name="Request",
                purpose="Sends requests.",
                source_component="api",
                target_component="service",
                requirement_ids=["FR-001"],
            )
        ],
    )

    ArchitectureValidator().validate(design)


def test_unknown_interface_source_is_rejected() -> None:
    design = SystemDesignArtifact(
        architecture_summary="Invalid.",
        components=[
            DesignComponent(
                id="api",
                name="API",
                responsibility="Handles requests.",
            )
        ],
        interfaces=[
            DesignInterface(
                id="interface-1",
                name="Invalid",
                purpose="Invalid reference.",
                source_component="missing",
                target_component="api",
            )
        ],
    )

    with pytest.raises(ArchitectureValidationError):
        ArchitectureValidator().validate(design)


def test_unknown_interface_target_is_rejected() -> None:
    design = SystemDesignArtifact(
        architecture_summary="Invalid.",
        components=[
            DesignComponent(
                id="api",
                name="API",
                responsibility="Handles requests.",
            )
        ],
        interfaces=[
            DesignInterface(
                id="interface-1",
                name="Invalid",
                purpose="Invalid reference.",
                source_component="api",
                target_component="missing",
            )
        ],
    )

    with pytest.raises(ArchitectureValidationError):
        ArchitectureValidator().validate(design)


def test_self_interface_is_rejected() -> None:
    design = SystemDesignArtifact(
        architecture_summary="Invalid.",
        components=[
            DesignComponent(
                id="api",
                name="API",
                responsibility="Handles requests.",
            )
        ],
        interfaces=[
            DesignInterface(
                id="interface-1",
                name="Self",
                purpose="Invalid.",
                source_component="api",
                target_component="api",
            )
        ],
    )

    with pytest.raises(ArchitectureValidationError):
        ArchitectureValidator().validate(design)


def test_unknown_dependency_component_is_rejected() -> None:
    design = SystemDesignArtifact(
        architecture_summary="Invalid.",
        components=[
            DesignComponent(
                id="api",
                name="API",
                responsibility="Handles requests.",
            )
        ],
        external_dependencies=[
            ExternalDependency(
                id="storage",
                name="Storage",
                purpose="Stores documents.",
                used_by_components=["missing"],
            )
        ],
    )

    with pytest.raises(ArchitectureValidationError):
        ArchitectureValidator().validate(design)


def test_duplicate_component_ids_are_rejected() -> None:
    design = SystemDesignArtifact(
        architecture_summary="Invalid.",
        components=[
            DesignComponent(
                id="api",
                name="API",
                responsibility="Handles requests.",
            ),
            DesignComponent(
                id="api",
                name="API 2",
                responsibility="Duplicate.",
            ),
        ],
    )

    with pytest.raises(ArchitectureValidationError):
        ArchitectureValidator().validate(design)
