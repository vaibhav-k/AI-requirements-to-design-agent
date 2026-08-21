import pytest

from src.domain.design import (
    Actor,
    AzureServiceMapping,
    DesignComponent,
    DesignInterface,
    ExternalDependency,
    SupportingAzureService,
    SystemDesignArtifact,
)
from src.infrastructure.validator import (
    ArchitectureValidationError,
    ArchitectureValidator,
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


def test_interface_may_terminate_at_an_actor() -> None:
    """An interface's source/target may reference an `Actor.id`, not only
    a `DesignComponent.id` - a real user/external-system actor calling
    into a component, per the architecture-generation phase's
    "external systems/users" requirement."""

    design = SystemDesignArtifact(
        architecture_summary="Actor-facing architecture.",
        components=[
            DesignComponent(id="api", name="API", responsibility="Handles requests.")
        ],
        actors=[
            Actor(id="end-user", name="End User", kind="user", description="A user.")
        ],
        interfaces=[
            DesignInterface(
                id="user-api",
                name="Sign in",
                purpose="Authenticates.",
                source_component="end-user",
                target_component="api",
            )
        ],
    )

    validated = ArchitectureValidator().validate(design)
    assert validated == design


def test_interface_to_unknown_actor_is_rejected() -> None:
    design = SystemDesignArtifact(
        architecture_summary="Invalid.",
        components=[
            DesignComponent(id="api", name="API", responsibility="Handles requests.")
        ],
        interfaces=[
            DesignInterface(
                id="user-api",
                name="Sign in",
                purpose="Authenticates.",
                source_component="missing-actor",
                target_component="api",
            )
        ],
    )

    with pytest.raises(ArchitectureValidationError):
        ArchitectureValidator().validate(design)


def test_azure_mapping_to_unknown_component_is_rejected() -> None:
    design = SystemDesignArtifact(
        architecture_summary="Invalid.",
        components=[
            DesignComponent(id="api", name="API", responsibility="Handles requests.")
        ],
        azure_mappings=[
            AzureServiceMapping(
                id="map-1",
                component_id="missing",
                azure_service="Azure App Service",
            )
        ],
    )

    with pytest.raises(ArchitectureValidationError):
        ArchitectureValidator().validate(design)


def test_azure_mapping_to_known_component_passes() -> None:
    design = SystemDesignArtifact(
        architecture_summary="Valid.",
        components=[
            DesignComponent(id="api", name="API", responsibility="Handles requests.")
        ],
        azure_mappings=[
            AzureServiceMapping(
                id="map-1",
                component_id="api",
                azure_service="Azure App Service",
                rationale="Managed PaaS hosting for the API.",
            )
        ],
    )

    validated = ArchitectureValidator().validate(design)
    assert validated == design


def test_supporting_service_referencing_unknown_component_is_rejected() -> None:
    design = SystemDesignArtifact(
        architecture_summary="Invalid.",
        components=[
            DesignComponent(id="api", name="API", responsibility="Handles requests.")
        ],
        supporting_azure_services=[
            SupportingAzureService(
                id="identity",
                azure_service="Microsoft Entra ID",
                category="Identity",
                purpose="Authenticates users.",
                applies_to_components=["missing"],
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
