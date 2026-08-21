from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP as MCPServer

from app.domain.design import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact
from app.domain.technical_design import TechnicalDesignArtifact
from app.domain.work_breakdown import WorkBreakdownArtifact
from app.infrastructure.composition import (
    build_design_tools_client,
    build_requirements_use_case,
    build_system_design_use_case,
    build_technical_design_use_case,
    build_work_breakdown_use_case,
)
from app.infrastructure.sync_bridge import run_sync

mcp = MCPServer(
    "AI Requirements to System Design Agent",
    instructions=(
        "Generate and validate structured software "
        "requirements and high-level system architectures."
    ),
)

# Composition-root singletons, constructed once at import time - the same
# shape the old ``RequirementsAnalyzer()``/``SystemDesignAnalyzer()``
# facades were constructed with, except each is now the real use case
# (``AnalyzeRequirementsUseCase``/``GenerateSystemDesignUseCase``) wired to
# a Microsoft Agent Framework adapter by ``app.infrastructure.composition``
# rather than a facade class reading env vars in its own ``__init__``. See
# ``tests/test_mcp.py`` for how tests replace ``.agent`` on these directly.
#
# ``_diagram_generator``/``_validator``/``_work_breakdown_exporter`` used
# to be (or, for the exporter, would otherwise have to be) concrete,
# in-process classes; all three live in ``backend/tools-service`` instead
# as part of the tools-service split (see README -> "Service
# Architecture"), so this external MCP server reaches them the same way
# the rest of the orchestrator does - via ``McpToolsClient`` over the
# internal design-tools MCP gateway (``backend/mcp-wrapper``).
# ``tests/test_mcp.py`` replaces these attributes directly, the same
# pattern it already uses for
# ``_requirements_analyzer``/``_design_analyzer``/``_work_breakdown_analyzer``.
_requirements_analyzer = build_requirements_use_case()
_design_analyzer = build_system_design_use_case()
_work_breakdown_analyzer = build_work_breakdown_use_case()
_technical_design_writer = build_technical_design_use_case()
_design_tools_client = build_design_tools_client()
_diagram_generator = _design_tools_client
_validator = _design_tools_client
_work_breakdown_exporter = _design_tools_client
_document_exporter = _design_tools_client


@mcp.tool()
def analyze_requirements(
    user_input: str,
) -> str:
    """Analyze free-text input into a structured requirements artifact.

    This is the entry point of the requirements-to-architecture flow - the
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
    version: int = 1,
    generated_at: str = "TBD",
) -> str:
    """Generate both required architecture diagrams (Logical Architecture
    + Azure Service Mapping) and return them as a JSON object:
    ``{"logical_svg": "...", "azure_mapping_svg": "..."}``.

    ``version``/``generated_at`` feed each diagram's deterministic
    metadata block - see ``DiagramMetadata``.
    """

    design = SystemDesignArtifact.model_validate_json(design_json)

    _validator.validate(design)

    diagrams = _diagram_generator.generate(design, version, generated_at)

    return diagrams.model_dump_json()


@mcp.tool()
def generate_work_breakdown(
    requirements_json: str,
    design_json: str,
) -> str:
    """Generate a Feature -> Story -> Task work breakdown, traceable back
    to the supplied requirements and architecture.

    Args:
        requirements_json: JSON RequirementsArtifact the breakdown must
            trace back to (unchanged from the original
            generate_system_design call).
        design_json: JSON SystemDesignArtifact the breakdown must trace
            back to.
    """

    requirements = RequirementsArtifact.model_validate_json(requirements_json)
    design = SystemDesignArtifact.model_validate_json(design_json)

    breakdown = run_sync(
        _work_breakdown_analyzer.execute(requirements, design),
        caller="generate_work_breakdown",
    )

    return breakdown.model_dump_json(indent=2)


@mcp.tool()
def refine_work_breakdown(
    user_input: str,
    requirements_json: str,
    design_json: str,
    breakdown_json: str,
) -> str:
    """Refine an existing work breakdown with new user input.

    Uses the previous breakdown as context, the same as
    refine_architecture: still-valid Features/Stories/Tasks are
    preserved, and the requested change is applied on top rather than
    regenerating the breakdown from scratch.

    Args:
        user_input: The requested change to apply to the previous breakdown.
        requirements_json: JSON RequirementsArtifact the breakdown must
            still trace back to.
        design_json: JSON SystemDesignArtifact the breakdown must still
            trace back to.
        breakdown_json: JSON WorkBreakdownArtifact from a prior
            generate_work_breakdown/refine_work_breakdown call.
    """

    requirements = RequirementsArtifact.model_validate_json(requirements_json)
    design = SystemDesignArtifact.model_validate_json(design_json)
    previous_breakdown = WorkBreakdownArtifact.model_validate_json(breakdown_json)

    breakdown = run_sync(
        _work_breakdown_analyzer.execute(
            requirements,
            design,
            previous_breakdown=previous_breakdown,
            refinement_input=user_input,
        ),
        caller="refine_work_breakdown",
    )

    return breakdown.model_dump_json(indent=2)


@mcp.tool()
def export_work_breakdown_csv(
    breakdown_json: str,
    requirements_json: str,
    design_json: str,
) -> str:
    """Validate a work breakdown's traceability and render it to CSV.

    Args:
        breakdown_json: JSON WorkBreakdownArtifact from a prior
            generate_work_breakdown/refine_work_breakdown call.
        requirements_json: JSON RequirementsArtifact the breakdown was
            generated from - used to catch fabricated/uncovered
            requirement IDs.
        design_json: JSON SystemDesignArtifact the breakdown was
            generated from - used to catch fabricated/uncovered
            architecture IDs.
    """

    breakdown = WorkBreakdownArtifact.model_validate_json(breakdown_json)
    requirements = RequirementsArtifact.model_validate_json(requirements_json)
    design = SystemDesignArtifact.model_validate_json(design_json)

    export = _work_breakdown_exporter.export(breakdown, requirements, design)

    return export.model_dump_json(indent=2)


@mcp.tool()
def generate_technical_design(
    requirements_json: str,
    design_json: str,
    work_breakdown_json: str,
) -> str:
    """Compile a technical design document, traceable back to the
    supplied requirements, architecture, and work breakdown.

    Args:
        requirements_json: JSON RequirementsArtifact the document must
            trace back to.
        design_json: JSON SystemDesignArtifact the document must trace
            back to.
        work_breakdown_json: JSON WorkBreakdownArtifact the document must
            trace back to.
    """

    requirements = RequirementsArtifact.model_validate_json(requirements_json)
    design = SystemDesignArtifact.model_validate_json(design_json)
    work_breakdown = WorkBreakdownArtifact.model_validate_json(work_breakdown_json)

    document = run_sync(
        _technical_design_writer.execute(requirements, design, work_breakdown),
        caller="generate_technical_design",
    )

    return document.model_dump_json(indent=2)


@mcp.tool()
def refine_technical_design(
    user_input: str,
    requirements_json: str,
    design_json: str,
    work_breakdown_json: str,
    document_json: str,
) -> str:
    """Refine an existing technical design document with new user input.

    Uses the previous document as context, the same as
    refine_work_breakdown: still-accurate sections are preserved, and the
    requested change is applied on top rather than regenerating the
    document from scratch.

    Args:
        user_input: The requested change to apply to the previous document.
        requirements_json: JSON RequirementsArtifact the document must
            still trace back to.
        design_json: JSON SystemDesignArtifact the document must still
            trace back to.
        work_breakdown_json: JSON WorkBreakdownArtifact the document must
            still trace back to.
        document_json: JSON TechnicalDesignArtifact from a prior
            generate_technical_design/refine_technical_design call.
    """

    requirements = RequirementsArtifact.model_validate_json(requirements_json)
    design = SystemDesignArtifact.model_validate_json(design_json)
    work_breakdown = WorkBreakdownArtifact.model_validate_json(work_breakdown_json)
    previous_document = TechnicalDesignArtifact.model_validate_json(document_json)

    document = run_sync(
        _technical_design_writer.execute(
            requirements,
            design,
            work_breakdown,
            previous_document=previous_document,
            refinement_input=user_input,
        ),
        caller="refine_technical_design",
    )

    return document.model_dump_json(indent=2)


@mcp.tool()
def export_technical_design_docx(
    document_json: str,
    design_json: str,
    requirements_json: str,
    work_breakdown_json: str,
) -> str:
    """Render a technical design document to ``.docx``, with the approved
    architecture diagram embedded.

    Args:
        document_json: JSON TechnicalDesignArtifact from a prior
            generate_technical_design/refine_technical_design call.
        design_json: JSON SystemDesignArtifact whose architecture diagram
            is embedded in the rendered document.
        requirements_json: JSON RequirementsArtifact referenced by the
            document's traceability appendix.
        work_breakdown_json: JSON WorkBreakdownArtifact referenced by the
            document's traceability appendix.
    """

    document = TechnicalDesignArtifact.model_validate_json(document_json)
    design = SystemDesignArtifact.model_validate_json(design_json)
    requirements = RequirementsArtifact.model_validate_json(requirements_json)
    work_breakdown = WorkBreakdownArtifact.model_validate_json(work_breakdown_json)

    export = _document_exporter.export_document(
        document, design, requirements, work_breakdown
    )

    return export.model_dump_json(indent=2)


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


@mcp.resource(
    "work-breakdown://schema",
)
def work_breakdown_schema() -> str:
    """Return the WorkBreakdownArtifact JSON schema."""

    return json.dumps(
        WorkBreakdownArtifact.model_json_schema(),
        indent=2,
    )


@mcp.resource(
    "technical-design://schema",
)
def technical_design_schema() -> str:
    """Return the TechnicalDesignArtifact JSON schema."""

    return json.dumps(
        TechnicalDesignArtifact.model_json_schema(),
        indent=2,
    )


def main() -> None:
    """Run the MCP server over stdio."""

    mcp.run()


if __name__ == "__main__":
    main()
