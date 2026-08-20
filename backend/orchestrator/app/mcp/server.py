from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP as MCPServer

from app.domain.design import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact
from app.infrastructure.composition import (
    build_design_tools_client,
    build_requirements_use_case,
    build_system_design_use_case,
)
from app.infrastructure.sync_bridge import run_sync

mcp = MCPServer(
    "AI Requirements to System Design Agent",
    instructions=(
        "Generate and validate structured software "
        "requirements and high-level system architectures."
    ),
)

# Composition-root singletons, constructed once at import time — the same
# shape the old ``RequirementsAnalyzer()``/``SystemDesignAnalyzer()``
# facades were constructed with, except each is now the real use case
# (``AnalyzeRequirementsUseCase``/``GenerateSystemDesignUseCase``) wired to
# a Microsoft Agent Framework adapter by ``app.infrastructure.composition``
# rather than a facade class reading env vars in its own ``__init__``. See
# ``tests/test_mcp.py`` for how tests replace ``.agent`` on these directly.
#
# ``_diagram_generator``/``_validator`` used to be the concrete, in-process
# ``ArchitectureDiagramGenerator``/``ArchitectureValidator`` classes; both
# moved to ``backend/tools-service`` as part of the tools-service split
# (see README -> "Service Architecture"), so this external MCP server now
# reaches them the same way the rest of the orchestrator does — via
# ``McpToolsClient`` over the internal design-tools MCP gateway
# (``backend/mcp-wrapper``). ``tests/test_mcp.py`` replaces these two
# attributes directly, the same pattern it already uses for
# ``_requirements_analyzer``/``_design_analyzer``.
_requirements_analyzer = build_requirements_use_case()
_design_analyzer = build_system_design_use_case()
_design_tools_client = build_design_tools_client()
_diagram_generator = _design_tools_client
_validator = _design_tools_client


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

    requirements = run_sync(
        _requirements_analyzer.execute(user_input),
        caller="analyze_requirements",
    )

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

    requirements = run_sync(
        _requirements_analyzer.execute(
            user_input,
            previous_artifact=previous,
        ),
        caller="refine_requirements",
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

    design = run_sync(
        _design_analyzer.execute(requirements),
        caller="generate_system_design",
    )

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

    design = run_sync(
        _design_analyzer.execute(
            requirements,
            previous_design=previous_design,
            refinement_input=user_input,
        ),
        caller="refine_architecture",
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
