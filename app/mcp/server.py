from __future__ import annotations

import json

from mcp.server import MCPServer

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

_design_analyzer = SystemDesignAnalyzer()
_diagram_generator = ArchitectureDiagramGenerator()
_validator = ArchitectureValidator()


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
