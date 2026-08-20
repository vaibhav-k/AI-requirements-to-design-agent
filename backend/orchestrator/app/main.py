"""
This module provides a command-line interface (CLI) for the AI Requirements → System
Design Agent. It allows users to input system requirements, analyze them, and generate
a high-level system architecture.

To run the CLI, execute this script in a terminal.
The user will be prompted to describe the system they want to build,
and the agent will analyze the requirements and generate a system design.

To use the web interface, run uvicorn app.web.main:app --reload
Navigate to http://127.0.0.1:8000/docs to get the Swagger UI for the API endpoints.
"""

from __future__ import annotations

from app.application.errors import (
    ArchitectureValidationError,
    DesignGenerationError,
    DiagramGenerationError,
)
from app.design.session import (
    ArchitectureSession,
    DesignGenerationWorkflowError,
)
from app.domain.design import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact, StoredArtifact
from app.infrastructure.artifact_store import (
    AZURE_CONNECTION_STRING,
    AZURE_CONTAINER,
    ArtifactStore,
)
from app.infrastructure.composition import (
    build_design_tools_client,
    build_requirements_use_case,
    build_system_design_use_case,
)
from app.session import DesignSession


def display_requirements(artifact: RequirementsArtifact) -> None:
    """Display the requirements artifact in the CLI."""

    print("\n")
    print("=" * 80)
    print("SYSTEM UNDERSTANDING")
    print("=" * 80)

    print(f"\n{artifact.summary}")

    print("\nBUSINESS GOAL")
    print("-" * 80)
    print(artifact.business_goal)

    print("\nACTORS")
    print("-" * 80)

    for actor in artifact.actors:
        print(f"- {actor.name}: {actor.description}")

    print("\nFUNCTIONAL REQUIREMENTS")
    print("-" * 80)

    for requirement in artifact.functional_requirements:
        print(f"[{requirement.id}] [{requirement.priority}] {requirement.description}")

    print("\nNON-FUNCTIONAL REQUIREMENTS")
    print("-" * 80)

    for requirement in artifact.non_functional_requirements:
        print(f"[{requirement.id}] [{requirement.priority}] {requirement.description}")

    print("\nDATA REQUIREMENTS")
    print("-" * 80)

    for item in artifact.data_requirements:
        print(f"- {item}")

    print("\nINTEGRATION REQUIREMENTS")
    print("-" * 80)

    for item in artifact.integration_requirements:
        print(f"- {item}")

    print("\nCONSTRAINTS")
    print("-" * 80)

    for item in artifact.constraints:
        print(f"- {item}")

    print("\nASSUMPTIONS")
    print("-" * 80)

    if artifact.assumptions:
        for assumption in artifact.assumptions:
            print(
                f"[{assumption.id}] [{assumption.confidence}] {assumption.assumption}"
            )
            print(f"    Reason: {assumption.reason}")
    else:
        print("No assumptions identified.")

    print("\nOPEN QUESTIONS")
    print("-" * 80)

    if artifact.open_questions:
        for question in artifact.open_questions:
            blocking = "BLOCKING" if question.blocking else "NON-BLOCKING"

            print(f"[{question.id}] [{blocking}] {question.question}")
            print(f"    Reason: {question.reason}")
    else:
        print("No open questions identified.")

    print("=" * 80)


def _print_design_components(design: SystemDesignArtifact) -> None:
    print("\nARCHITECTURE COMPONENTS")
    print("-" * 80)

    if design.components:
        for component in design.components:
            requirements = (
                ", ".join(component.requirement_ids)
                if component.requirement_ids
                else "none"
            )

            print(f"[{component.id}] {component.name}: {component.responsibility}")
            print(f"    Requirements: {requirements}")
    else:
        print("No architecture components identified.")


def _print_design_interfaces(design: SystemDesignArtifact) -> None:
    print("\nARCHITECTURE INTERFACES")
    print("-" * 80)

    if design.interfaces:
        for interface in design.interfaces:
            requirements = (
                ", ".join(interface.requirement_ids)
                if interface.requirement_ids
                else "none"
            )

            print(
                f"[{interface.id}] "
                f"{interface.name}: "
                f"{interface.source_component} "
                f"-> "
                f"{interface.target_component}"
            )
            print(f"    Purpose: {interface.purpose}")
            print(f"    Requirements: {requirements}")
    else:
        print("No architecture interfaces identified.")


def _print_design_external_dependencies(design: SystemDesignArtifact) -> None:
    print("\nEXTERNAL DEPENDENCIES")
    print("-" * 80)

    if design.external_dependencies:
        for dependency in design.external_dependencies:
            components = (
                ", ".join(dependency.used_by_components)
                if dependency.used_by_components
                else "none"
            )

            print(f"[{dependency.id}] {dependency.name}: {dependency.purpose}")
            print(f"    Used by: {components}")
    else:
        print("No external dependencies identified.")


def _print_design_assumptions(design: SystemDesignArtifact) -> None:
    print("\nARCHITECTURE ASSUMPTIONS")
    print("-" * 80)

    if design.assumptions:
        for assumption in design.assumptions:
            print(f"[{assumption.id}] {assumption.assumption}")
            print(f"    Reason: {assumption.reason}")
    else:
        print("No architecture assumptions identified.")


def _print_design_open_questions(design: SystemDesignArtifact) -> None:
    print("\nARCHITECTURE OPEN QUESTIONS")
    print("-" * 80)

    if design.open_questions:
        for question in design.open_questions:
            print(f"[{question.id}] {question.question}")
            print(f"    Reason: {question.reason}")
    else:
        print("No architecture questions identified.")


def display_design(design: SystemDesignArtifact) -> None:
    """Display a generated architecture.

    Delegates each section to its own ``_print_design_*`` helper -
    previously all inlined here, which pushed this one function past a
    reasonable cyclomatic-complexity threshold (15 branches). Each helper
    is a single, independently readable "if there's data, list it,
    otherwise say so" block.
    """

    print("\nArchitecture Summary")
    print("-" * 80)
    print(design.architecture_summary)

    _print_design_components(design)
    _print_design_interfaces(design)
    _print_design_external_dependencies(design)
    _print_design_assumptions(design)
    _print_design_open_questions(design)


def _accept_and_generate_architecture(
    session: DesignSession,
    store: ArtifactStore,
    artifact: StoredArtifact,
) -> bool:
    """Handle the "1. Accept" menu choice.

    Generates the architecture from the accepted requirements, displays and
    reports it on success, or prints a labeled failure message on any of
    the (mutually exclusive) generation-error types. Returns ``True`` when
    the interactive loop should stop (a design was produced), ``False``
    when it should loop back to the menu (a recoverable generation error
    was already reported to the user).

    Extracted out of ``run`` - inlined, this ``try``/``except`` cascade
    plus the display/print calls pushed ``run`` well past a reasonable
    statement-count threshold (59/50).
    """
    print("\nRequirements accepted.")
    print("\nGenerating high-level system architecture...")

    try:
        design_tools_client = build_design_tools_client()
        design_session = ArchitectureSession(
            analyzer=build_system_design_use_case(),
            diagram_generator=design_tools_client,
            validator=design_tools_client,
            store=store,
            session_id=session.session_id,
        )

        design_result = design_session.generate(artifact.requirements)

    except ArchitectureValidationError as exc:
        print("\nArchitecture validation failed:")
        print(exc)
        return False

    except DesignGenerationError as exc:
        print("\nArchitecture generation failed:")
        print(exc)
        return False

    except DiagramGenerationError as exc:
        print("\nArchitecture diagram generation failed:")
        print(exc)
        return False

    except DesignGenerationWorkflowError as exc:
        print("\nArchitecture workflow failed:")
        print(exc)
        return False

    display_design(design_result.design)

    print("\nSaved design:")
    print(f"  Version: v{design_result.version}")
    print(f"  JSON: {design_result.design_blob}")
    print(f"  SVG:  {design_result.diagram_blob}")

    return True


def run() -> None:
    """Run the interactive requirements analyzer."""

    analyzer = build_requirements_use_case()

    store = ArtifactStore(
        connection_string=AZURE_CONNECTION_STRING,
        container_name=AZURE_CONTAINER,
    )

    session = DesignSession(
        analyzer,
        store,
    )

    print("=" * 80)
    print("AI REQUIREMENTS → SYSTEM DESIGN AGENT")
    print("=" * 80)

    print("\nDescribe what you want to build.")
    print("Type 'exit' to quit.\n")

    user_input = input("> ").strip()

    if user_input.lower() == "exit":
        return

    while True:
        artifact = session.analyze(user_input)

        display_requirements(artifact.requirements)

        print("\n")
        print("What would you like to do?")
        print("  1. Accept")
        print("  2. Refine")
        print("  3. Exit")

        choice = input("\n> ").strip()

        if choice == "1":
            if _accept_and_generate_architecture(session, store, artifact):
                break
            continue

        if choice == "2":
            print("\nDescribe what should be changed, added, or clarified.")

            user_input = input("\n> ").strip()

            if user_input.lower() == "exit":
                break

            continue

        if choice == "3":
            break

        print("Please choose 1, 2, or 3.")


if __name__ == "__main__":
    run()
