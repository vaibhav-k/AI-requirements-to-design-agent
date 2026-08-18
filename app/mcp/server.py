from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP as MCPServer

from app.analyzer import RequirementsAnalyzer
from app.design.analyzer import SystemDesignAnalyzer
from app.design.diagram import ArchitectureDiagramGenerator
from app.design.models import SystemDesignArtifact
from app.design.validator import ArchitectureValidator
from app.models import RequirementsArtifact

mcp = MCPServer(
    "AI Requirements to System Design Agent",
    instructions=(
        "Generate and validate structured software "
        "requirements and high-level system architectures."
    ),
)

_requirements_analyzer = RequirementsAnalyzer()
_design_analyzer = SystemDesignAnalyzer()
_diagram_generator = ArchitectureDiagramGenerator()
_validator = ArchitectureValidator()


@mcp.tool()
def analyze_requirements(
    user_input: str,
) -> str:
    """Analyze free-text input into a structured requirements artifact.

    This is the entry point of the requirements-to-architecture flow — the
    first tool an MCP client calls, before generate_system_design.

    Args:
        user_input: Free-text description of what the user wants to build.
    """

    requirements = _requirements_analyzer.analyze(user_input)

    return requirements.model_dump_json(indent=2)


@mcp.tool()
def refine_requirements(
    user_input: str,
    requirements_json: str,
) -> str:
    """Refine an existing requirements artifact with new user input.

    Uses the previous artifact as context, the same as the CLI's/web API's
    "Refine" step: still-valid information is preserved, and the new input
    is layered on top rather than starting the analysis from scratch.

    Args:
        user_input: New information to apply to the previous analysis.
        requirements_json: JSON RequirementsArtifact from a prior
            analyze_requirements/refine_requirements call.
    """

    previous = RequirementsArtifact.model_validate_json(requirements_json)

    requirements = _requirements_analyzer.analyze(
        user_input,
        previous_artifact=previous,
    )

    return requirements.model_dump_json(indent=2)


@mcp.tool()
def generate_system_design(
    requirements_json: str,
) -> str:
    """Generate a validated high-level system architecture.

    Args:
        requirements_json: JSON RequirementsArtifact.
    """

    requirements = RequirementsArtifact.model_validate_json(requirements_json)

    design = _design_analyzer.analyze(requirements)

    return design.model_dump_json(indent=2)


@mcp.tool()
def refine_architecture(
    user_input: str,
    requirements_json: str,
    design_json: str,
) -> str:
    """Refine an existing system design artifact with new user input.

    Uses the previous design as context, the same as the web API's
    "refine-architecture" step: still-valid components, interfaces, and
    external dependencies are preserved, and the requested change is
    applied on top rather than regenerating the architecture from scratch.

    Args:
        user_input: The requested change to apply to the previous design.
        requirements_json: JSON RequirementsArtifact the design must still
            satisfy (unchanged from the original generate_system_design call).
        design_json: JSON SystemDesignArtifact from a prior
            generate_system_design/refine_architecture call.
    """

    requirements = RequirementsArtifact.model_validate_json(requirements_json)
    previous_design = SystemDesignArtifact.model_validate_json(design_json)

    design = _design_analyzer.analyze(
        requirements,
        previous_design=previous_design,
        refinement_input=user_input,
    )

    return design.model_dump_json(indent=2)


@mcp.tool()
def validate_system_design(
    design_json: str,
) -> str:
    """Validate a SystemDesignArtifact."""

    design = SystemDesignArtifact.model_validate_json(design_json)

    _validator.validate(design)

    return json.dumps(
        {
            "valid": True,
            "message": ("System design is semantically valid."),
        },
        indent=2,
    )


@mcp.tool()
def generate_architecture_diagram(
    design_json: str,
) -> str:
    """Generate an SVG architecture diagram."""

    design = SystemDesignArtifact.model_validate_json(design_json)

    _validator.validate(design)

    return _diagram_generator.generate(design)


@mcp.resource(
    "requirements://schema",
)
def requirements_schema() -> str:
    """Return the RequirementsArtifact JSON schema."""

    return json.dumps(
        RequirementsArtifact.model_json_schema(),
        indent=2,
    )


@mcp.resource(
    "design://schema",
)
def design_schema() -> str:
    """Return the SystemDesignArtifact JSON schema."""

    return json.dumps(
        SystemDesignArtifact.model_json_schema(),
        indent=2,
    )


def main() -> None:
    """Run the MCP server over stdio."""

    mcp.run()


if __name__ == "__main__":
    main()
