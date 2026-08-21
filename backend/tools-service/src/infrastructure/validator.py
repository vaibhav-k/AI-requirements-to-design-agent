from __future__ import annotations

from src.domain.design import (
    AzureServiceMapping,
    DesignInterface,
    ExternalDependency,
    SupportingAzureService,
    SystemDesignArtifact,
)
from src.domain.errors import ArchitectureValidationError

__all__ = ["ArchitectureValidationError", "ArchitectureValidator"]


class ArchitectureValidator:
    """Validate the semantic integrity of a system architecture.

    ``validate`` itself only assembles the error list and raises - each
    individual rule lives in its own small, independently testable method
    below, rather than one long function with every check inlined. That
    keeps each method's own cognitive complexity low instead of just
    moving the problem around.
    """

    def validate(
        self,
        design: SystemDesignArtifact,
    ) -> SystemDesignArtifact:
        """Validate and return the architecture."""

        component_ids = {component.id for component in design.components}
        actor_ids = {actor.id for actor in design.actors}
        # Interface endpoints may reference either a component or an
        # actor (see `Actor`'s docstring) - the diagram-generation layer
        # tells them apart by which set an id falls into, but validation
        # just needs the union.
        endpoint_ids = component_ids | actor_ids
        dependency_ids = {dependency.id for dependency in design.external_dependencies}
        # `AzureServiceMapping.component_id` may point at a component, an
        # actor, or an external dependency - whichever this design
        # actually maps to Azure.
        mappable_ids = endpoint_ids | dependency_ids

        errors: list[str] = [
            *self._duplicate_id_errors(
                [component.id for component in design.components],
                "Component",
            ),
            *self._duplicate_id_errors(
                [interface.id for interface in design.interfaces],
                "Interface",
            ),
            *self._duplicate_id_errors(
                [dependency.id for dependency in design.external_dependencies],
                "External dependency",
            ),
            *self._duplicate_id_errors(
                [actor.id for actor in design.actors],
                "Actor",
            ),
            *self._duplicate_id_errors(
                [mapping.id for mapping in design.azure_mappings],
                "Azure service mapping",
            ),
            *self._duplicate_id_errors(
                [service.id for service in design.supporting_azure_services],
                "Supporting Azure service",
            ),
            *self._validate_interfaces(design.interfaces, endpoint_ids),
            *self._validate_external_dependencies(
                design.external_dependencies,
                component_ids,
            ),
            *self._validate_azure_mappings(design.azure_mappings, mappable_ids),
            *self._validate_supporting_services(
                design.supporting_azure_services, mappable_ids
            ),
            *self._validate_requirement_ids(self._collect_requirement_ids(design)),
        ]

        if errors:
            raise ArchitectureValidationError(
                "Architecture validation failed:\n- " + "\n- ".join(errors)
            )

        return design

    # ---------------------------------------------------------
    # Unique IDs (components, interfaces, external dependencies)
    # ---------------------------------------------------------

    @staticmethod
    def _duplicate_id_errors(
        ids: list[str],
        label: str,
    ) -> list[str]:
        """Return a single error if `ids` contains a duplicate."""

        if len(ids) == len(set(ids)):
            return []

        return [f"{label} IDs must be unique."]

    # ---------------------------------------------------------
    # Interfaces
    # ---------------------------------------------------------

    @staticmethod
    def _validate_interfaces(
        interfaces: list[DesignInterface],
        component_ids: set[str],
    ) -> list[str]:
        errors: list[str] = []

        for interface in interfaces:
            errors.extend(
                ArchitectureValidator._validate_single_interface(
                    interface,
                    component_ids,
                )
            )

        return errors

    @staticmethod
    def _validate_single_interface(
        interface: DesignInterface,
        component_ids: set[str],
    ) -> list[str]:
        errors: list[str] = []

        if interface.source_component not in component_ids:
            errors.append(
                f"Interface '{interface.id}' references unknown "
                f"source component "
                f"'{interface.source_component}'."
            )

        if interface.target_component not in component_ids:
            errors.append(
                f"Interface '{interface.id}' references unknown "
                f"target component "
                f"'{interface.target_component}'."
            )

        if interface.source_component == interface.target_component:
            errors.append(
                f"Interface '{interface.id}' cannot connect a component to itself."
            )

        return errors

    # ---------------------------------------------------------
    # External dependencies
    # ---------------------------------------------------------

    @staticmethod
    def _validate_external_dependencies(
        dependencies: list[ExternalDependency],
        component_ids: set[str],
    ) -> list[str]:
        errors: list[str] = []

        for dependency in dependencies:
            errors.extend(
                ArchitectureValidator._validate_single_dependency(
                    dependency,
                    component_ids,
                )
            )

        return errors

    @staticmethod
    def _validate_single_dependency(
        dependency: ExternalDependency,
        component_ids: set[str],
    ) -> list[str]:
        return [
            f"External dependency '{dependency.id}' references unknown "
            f"component '{component_id}'."
            for component_id in dependency.used_by_components
            if component_id not in component_ids
        ]

    # ---------------------------------------------------------
    # Azure Service Mapping / supporting services traceability
    # ---------------------------------------------------------
    #
    # These two checks are what actually enforces the architecture-
    # generation phase's "must be directly traceable" requirement at the
    # data layer: an `AzureServiceMapping`/`SupportingAzureService` that
    # references an id absent from the Logical Architecture side would
    # otherwise render a mapping-diagram node with no corresponding
    # logical node to trace back to.

    @staticmethod
    def _validate_azure_mappings(
        mappings: list[AzureServiceMapping],
        mappable_ids: set[str],
    ) -> list[str]:
        return [
            f"Azure service mapping '{mapping.id}' references unknown "
            f"component/actor/external dependency '{mapping.component_id}'."
            for mapping in mappings
            if mapping.component_id not in mappable_ids
        ]

    @staticmethod
    def _validate_supporting_services(
        services: list[SupportingAzureService],
        mappable_ids: set[str],
    ) -> list[str]:
        errors: list[str] = []

        for service in services:
            errors.extend(
                f"Supporting Azure service '{service.id}' references "
                f"unknown component/actor/external dependency '{component_id}'."
                for component_id in service.applies_to_components
                if component_id not in mappable_ids
            )

        return errors

    # ---------------------------------------------------------
    # Requirement traceability
    # ---------------------------------------------------------
    #
    # Traceability IDs are checked structurally here. The actual
    # requirement set is supplied at the workflow level if cross-artifact
    # validation is enabled.

    @staticmethod
    def _collect_requirement_ids(design: SystemDesignArtifact) -> set[str]:
        requirement_ids: set[str] = set()

        for component in design.components:
            requirement_ids.update(component.requirement_ids)

        for interface in design.interfaces:
            requirement_ids.update(interface.requirement_ids)

        return requirement_ids

    @staticmethod
    def _validate_requirement_ids(requirement_ids: set[str]) -> list[str]:
        # One message per blank/whitespace-only id in the set (matching the
        # original inline loop's behavior exactly) rather than deduping to a
        # single message - `requirement_ids` is a set, so this can only
        # repeat if more than one distinct blank-ish string (e.g. "" and
        # " ") is present.
        return [
            "Requirement traceability IDs cannot be empty."
            for requirement_id in requirement_ids
            if not requirement_id.strip()
        ]
