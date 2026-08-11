from __future__ import annotations

from app.design.models import SystemDesignArtifact


class ArchitectureValidationError(ValueError):
    """Raised when an architecture fails semantic validation."""


class ArchitectureValidator:
    """Validate the semantic integrity of a system architecture."""

    def validate(
        self,
        design: SystemDesignArtifact,
    ) -> SystemDesignArtifact:
        """Validate and return the architecture."""

        errors: list[str] = []

        # ---------------------------------------------------------
        # Component IDs
        # ---------------------------------------------------------

        component_ids = [component.id for component in design.components]

        if len(component_ids) != len(set(component_ids)):
            errors.append("Component IDs must be unique.")

        component_id_set = set(component_ids)

        # ---------------------------------------------------------
        # Interface IDs
        # ---------------------------------------------------------

        interface_ids = [interface.id for interface in design.interfaces]

        if len(interface_ids) != len(set(interface_ids)):
            errors.append("Interface IDs must be unique.")

        # ---------------------------------------------------------
        # External dependency IDs
        # ---------------------------------------------------------

        dependency_ids = [dependency.id for dependency in design.external_dependencies]

        if len(dependency_ids) != len(set(dependency_ids)):
            errors.append("External dependency IDs must be unique.")

        # ---------------------------------------------------------
        # Interfaces
        # ---------------------------------------------------------

        for interface in design.interfaces:
            if interface.source_component not in component_id_set:
                errors.append(
                    f"Interface '{interface.id}' references unknown "
                    f"source component "
                    f"'{interface.source_component}'."
                )

            if interface.target_component not in component_id_set:
                errors.append(
                    f"Interface '{interface.id}' references unknown "
                    f"target component "
                    f"'{interface.target_component}'."
                )

            if interface.source_component == interface.target_component:
                errors.append(
                    f"Interface '{interface.id}' cannot connect a component to itself."
                )

        # ---------------------------------------------------------
        # External dependencies
        # ---------------------------------------------------------

        for dependency in design.external_dependencies:
            for component_id in dependency.used_by_components:
                if component_id not in component_id_set:
                    errors.append(
                        f"External dependency '{dependency.id}' "
                        f"references unknown component "
                        f"'{component_id}'."
                    )

        # ---------------------------------------------------------
        # Requirement traceability
        # ---------------------------------------------------------

        requirement_ids: set[str] = set()

        for component in design.components:
            requirement_ids.update(component.requirement_ids)

        for interface in design.interfaces:
            requirement_ids.update(interface.requirement_ids)

        # Traceability IDs are checked structurally here.
        # The actual requirement set is supplied at the workflow level
        # if cross-artifact validation is enabled.

        for requirement_id in requirement_ids:
            if not requirement_id.strip():
                errors.append("Requirement traceability IDs cannot be empty.")

        # ---------------------------------------------------------
        # Final result
        # ---------------------------------------------------------

        if errors:
            raise ArchitectureValidationError(
                "Architecture validation failed:\n- " + "\n- ".join(errors)
            )

        return design
