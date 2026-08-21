"""Composition root: wires Microsoft Agent Framework adapters into the
application layer's use cases.

This is the final destination the "strangler fig" facades
(``app/analyzer.py``, ``app/design/analyzer.py``, ``app/vision.py``) were
always meant to lead to - see README -> "Clean Architecture Migration".
Those facades used to read ``AZURE_OPENAI_*`` from the environment and
construct their own ``AgentFrameworkXAgent`` adapter inside ``__init__``,
which meant every one of them duplicated the same "require this env var
or raise" logic, and every call site got a concrete, already-wired
service handed to it with no single place that decided *how* it was
wired. Now that decision lives here, once, and every call site
(``app/api/dependencies.py``, ``app/mcp/server.py``, ``app/main.py``)
asks this module for a ready-to-use ``*UseCase`` instead of constructing
one of the old facade classes.

Nothing in ``app.application`` or ``app.domain`` imports this module -
only presentation-layer composition roots do.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from app.application.use_cases.analyze_requirements import AnalyzeRequirementsUseCase
from app.application.use_cases.classify_image import ClassifyImageUseCase
from app.application.use_cases.generate_system_design import (
    GenerateSystemDesignUseCase,
)
from app.application.use_cases.generate_technical_design import (
    GenerateTechnicalDesignUseCase,
)
from app.application.use_cases.generate_work_breakdown import (
    GenerateWorkBreakdownUseCase,
)
from app.application.use_cases.interpret_diagram_image import (
    InterpretDiagramImageUseCase,
)
from app.infrastructure.agents.diagram_image_interpreter_agent import (
    AgentFrameworkDiagramImageInterpreterAgent,
)
from app.infrastructure.agents.image_classifier_agent import (
    AgentFrameworkImageClassifierAgent,
)
from app.infrastructure.agents.requirements_agent import (
    AgentFrameworkRequirementsAgent,
)
from app.infrastructure.agents.system_design_agent import (
    AgentFrameworkSystemDesignAgent,
)
from app.infrastructure.agents.technical_writer_agent import (
    AgentFrameworkTechnicalWriterAgent,
)
from app.infrastructure.agents.work_breakdown_agent import (
    AgentFrameworkWorkBreakdownAgent,
)
from app.infrastructure.tools_client import McpToolsClient

load_dotenv()

_DEFAULT_DESIGN_TOOLS_MCP_URL = "http://localhost:8200/mcp/design-tools"


def _required_env(name: str) -> str:
    """Return a required environment variable, or raise a clear error."""

    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"{name} environment variable is required.")

    return value


def _resolved_model(model: str | None) -> str:
    return model or _required_env("AZURE_OPENAI_MODEL")


def build_requirements_use_case(
    model: str | None = None,
) -> AnalyzeRequirementsUseCase:
    """Build an ``AnalyzeRequirementsUseCase`` wired to a real Microsoft
    Agent Framework agent, reading Azure OpenAI configuration from the
    environment."""

    agent = AgentFrameworkRequirementsAgent(
        api_key=_required_env("AZURE_OPENAI_API_KEY"),
        endpoint=_required_env("AZURE_OPENAI_ENDPOINT"),
        model=_resolved_model(model),
    )

    return AnalyzeRequirementsUseCase(agent=agent)


def build_system_design_use_case(
    model: str | None = None,
) -> GenerateSystemDesignUseCase:
    """Build a ``GenerateSystemDesignUseCase`` wired to a real Microsoft
    Agent Framework agent, reading Azure OpenAI configuration from the
    environment."""

    agent = AgentFrameworkSystemDesignAgent(
        api_key=_required_env("AZURE_OPENAI_API_KEY"),
        endpoint=_required_env("AZURE_OPENAI_ENDPOINT"),
        model=_resolved_model(model),
    )

    return GenerateSystemDesignUseCase(agent=agent)


def build_image_classifier_use_case(
    model: str | None = None,
) -> ClassifyImageUseCase:
    """Build a ``ClassifyImageUseCase`` wired to a real Microsoft Agent
    Framework agent, reading Azure OpenAI configuration from the
    environment."""

    agent = AgentFrameworkImageClassifierAgent(
        api_key=_required_env("AZURE_OPENAI_API_KEY"),
        endpoint=_required_env("AZURE_OPENAI_ENDPOINT"),
        model=_resolved_model(model),
    )

    return ClassifyImageUseCase(agent=agent)


def build_diagram_interpreter_use_case(
    model: str | None = None,
) -> InterpretDiagramImageUseCase:
    """Build an ``InterpretDiagramImageUseCase`` wired to a real Microsoft
    Agent Framework agent, reading Azure OpenAI configuration from the
    environment."""

    agent = AgentFrameworkDiagramImageInterpreterAgent(
        api_key=_required_env("AZURE_OPENAI_API_KEY"),
        endpoint=_required_env("AZURE_OPENAI_ENDPOINT"),
        model=_resolved_model(model),
    )

    return InterpretDiagramImageUseCase(agent=agent)


def build_work_breakdown_use_case(
    model: str | None = None,
) -> GenerateWorkBreakdownUseCase:
    """Build a ``GenerateWorkBreakdownUseCase`` wired to a real Microsoft
    Agent Framework agent, reading Azure OpenAI configuration from the
    environment."""

    agent = AgentFrameworkWorkBreakdownAgent(
        api_key=_required_env("AZURE_OPENAI_API_KEY"),
        endpoint=_required_env("AZURE_OPENAI_ENDPOINT"),
        model=_resolved_model(model),
    )

    return GenerateWorkBreakdownUseCase(agent=agent)


def build_technical_design_use_case(
    model: str | None = None,
) -> GenerateTechnicalDesignUseCase:
    """Build a ``GenerateTechnicalDesignUseCase`` wired to a real
    Microsoft Agent Framework agent, reading Azure OpenAI configuration
    from the environment - the technical-design analogue of
    ``build_work_breakdown_use_case``."""

    agent = AgentFrameworkTechnicalWriterAgent(
        api_key=_required_env("AZURE_OPENAI_API_KEY"),
        endpoint=_required_env("AZURE_OPENAI_ENDPOINT"),
        model=_resolved_model(model),
    )

    return GenerateTechnicalDesignUseCase(agent=agent)


def build_design_tools_client() -> McpToolsClient:
    """Build the ``McpToolsClient`` shared by ``DiagramRendererPort``,
    ``ArchitectureValidatorPort``, and ``WorkBreakdownExporterPort`` call
    sites (``app/api/dependencies.py``, ``app/mcp/server.py``,
    ``app/main.py``).

    Unlike the agent builders above, this reads an optional (not required)
    env var - ``DESIGN_TOOLS_MCP_URL`` - since a sensible default exists
    for local development (``backend/mcp-wrapper``'s ``combined_main.py``
    default gateway host/port/path, see that service's README). Production
    deployments still set it explicitly to point at wherever
    ``backend/mcp-wrapper`` actually runs.
    """

    mcp_url = os.getenv("DESIGN_TOOLS_MCP_URL", _DEFAULT_DESIGN_TOOLS_MCP_URL)

    return McpToolsClient(mcp_url=mcp_url)
