import json

import pytest

from app.domain.design import (
    ArchitectureDiagrams,
    DesignComponent,
    SystemDesignArtifact,
)
from app.domain.requirements import Requirement, RequirementsArtifact
from app.domain.work_breakdown import WorkBreakdownArtifact, WorkBreakdownExport
from app.mcp import server as mcp_server
from app.mcp.server import (
    design_schema,
    requirements_schema,
    validate_system_design,
    work_breakdown_schema,
)


class _FakeRequirementsAgent:
    """A ``RequirementsAgentPort`` fake standing in for the Microsoft
    Agent Framework-backed adapter, injected into the module-level
    ``_requirements_analyzer`` singleton for the duration of a test (see
    ``mock_requirements_agent`` below) - no real Azure OpenAI call, no
    network. Mirrors the pattern in ``tests/test_analyzer.py``."""

    def __init__(self, artifact: RequirementsArtifact) -> None:
        self.artifact = artifact
        self.calls: list[tuple[str, RequirementsArtifact | None]] = []

    async def analyze(
        self,
        user_input: str,
        previous_artifact: RequirementsArtifact | None = None,
    ) -> RequirementsArtifact:
        self.calls.append((user_input, previous_artifact))
        return self.artifact


def _requirements_artifact(
    summary: str = "A requirements analysis.",
) -> RequirementsArtifact:
    """Create a minimal requirements artifact, matching the test fixtures
    used elsewhere for this model (test_analyzer.py, test_refinement.py)."""

    return RequirementsArtifact(
        summary=summary,
        business_goal="Understand user requirements.",
        actors=[],
        functional_requirements=[],
        non_functional_requirements=[],
        data_requirements=[],
        integration_requirements=[],
        constraints=[],
        assumptions=[],
        open_questions=[],
    )


@pytest.fixture
def mock_requirements_agent() -> _FakeRequirementsAgent:
    """Replace the module-level `_requirements_analyzer`'s underlying
    ``RequirementsAgentPort`` with a fake for the duration of a test - it's
    a singleton ``AnalyzeRequirementsUseCase`` constructed at import time by
    ``app.mcp.server`` (via ``app.infrastructure.composition``), so its
    ``.agent`` is patched in place rather than re-instantiating the whole
    use case."""

    fake_agent = _FakeRequirementsAgent(_requirements_artifact())
    mcp_server._requirements_analyzer.agent = fake_agent
    return fake_agent


class _FakeSystemDesignAgent:
    """A ``SystemDesignAgentPort`` fake - the design-generation analogue
    of ``_FakeRequirementsAgent`` above, injected into the module-level
    ``_design_analyzer`` singleton for the duration of a test."""

    def __init__(self, design: SystemDesignArtifact) -> None:
        self.design = design
        self.calls: list[
            tuple[RequirementsArtifact, SystemDesignArtifact | None, str | None]
        ] = []

    async def generate(
        self,
        requirements: RequirementsArtifact,
        previous_design: SystemDesignArtifact | None = None,
        refinement_input: str | None = None,
    ) -> SystemDesignArtifact:
        self.calls.append((requirements, previous_design, refinement_input))
        return self.design


@pytest.fixture
def mock_design_agent() -> _FakeSystemDesignAgent:
    """Replace the module-level `_design_analyzer`'s underlying
    ``SystemDesignAgentPort`` with a fake for the duration of a test -
    the design-generation analogue of `mock_requirements_agent` above."""

    fake_agent = _FakeSystemDesignAgent(
        SystemDesignArtifact(architecture_summary="A design.")
    )
    mcp_server._design_analyzer.agent = fake_agent
    return fake_agent


def test_design_schema_is_valid_json() -> None:
    result = design_schema()

    schema = json.loads(result)

    assert "properties" in schema
    assert "components" in schema["properties"]
    assert "external_dependencies" in schema["properties"]


def test_requirements_schema_is_valid_json() -> None:
    result = requirements_schema()

    schema = json.loads(result)

    assert "properties" in schema
    assert "functional_requirements" in schema["properties"]
    assert "open_questions" in schema["properties"]


def test_analyze_requirements_tool_returns_structured_artifact(
    mock_requirements_agent: _FakeRequirementsAgent,
) -> None:
    artifact = _requirements_artifact("A todo app for small teams.")
    mock_requirements_agent.artifact = artifact

    result = mcp_server.analyze_requirements("Build a todo app for small teams.")

    parsed = RequirementsArtifact.model_validate_json(result)

    assert parsed == artifact
    assert len(mock_requirements_agent.calls) == 1


def test_refine_requirements_tool_passes_previous_artifact_as_context(
    mock_requirements_agent: _FakeRequirementsAgent,
) -> None:
    previous = _requirements_artifact("Initial analysis.")
    refined = _requirements_artifact("Refined analysis.")
    mock_requirements_agent.artifact = refined

    result = mcp_server.refine_requirements(
        "Also support due dates.",
        previous.model_dump_json(),
    )

    parsed = RequirementsArtifact.model_validate_json(result)

    assert parsed == refined

    # Confirm refine_requirements actually threaded `previous` through to
    # the agent, rather than analyzing `user_input` in isolation.
    [(sent_input, sent_previous)] = mock_requirements_agent.calls
    assert sent_input == "Also support due dates."
    assert sent_previous == previous


def test_refine_architecture_tool_passes_previous_design_as_context(
    mock_design_agent: _FakeSystemDesignAgent,
) -> None:
    requirements = _requirements_artifact("A todo app for small teams.")
    previous_design = SystemDesignArtifact(
        architecture_summary="Original architecture."
    )
    refined_design = SystemDesignArtifact(architecture_summary="Refined architecture.")
    mock_design_agent.design = refined_design

    result = mcp_server.refine_architecture(
        "Add a notifications component.",
        requirements.model_dump_json(),
        previous_design.model_dump_json(),
    )

    parsed = SystemDesignArtifact.model_validate_json(result)

    assert parsed == refined_design

    # Confirm refine_architecture actually threaded the previous design
    # through as context, rather than generating a fresh architecture from
    # requirements alone.
    [(sent_requirements, sent_previous, sent_refinement_input)] = (
        mock_design_agent.calls
    )
    assert sent_requirements == requirements
    assert sent_previous == previous_design
    assert sent_refinement_input == "Add a notifications component."


class _FakeDesignToolsClient:
    """A ``DiagramRendererPort``/``ArchitectureValidatorPort`` fake standing
    in for ``app.infrastructure.tools_client.McpToolsClient`` - no real MCP
    round trip to ``backend/mcp-wrapper``/``backend/tools-service``, the
    same "patch the module-level singleton's dependency" pattern
    ``mock_requirements_agent``/``mock_design_agent`` use above.

    Since the tools-service split, this module's own
    ``_diagram_generator``/``_validator`` singletons are both the same
    ``McpToolsClient`` instance (see ``app/mcp/server.py``), so this one
    fake covers both.
    """

    def __init__(self, design: SystemDesignArtifact) -> None:
        self.design = design
        self.validate_calls: list[SystemDesignArtifact] = []
        self.generate_calls: list[SystemDesignArtifact] = []

    def validate(self, design: SystemDesignArtifact) -> SystemDesignArtifact:
        self.validate_calls.append(design)
        return self.design

    def generate(
        self, design: SystemDesignArtifact, version: int, generated_at: str
    ) -> ArchitectureDiagrams:
        self.generate_calls.append(design)
        return ArchitectureDiagrams(
            logical_svg="<svg>logical</svg>", azure_mapping_svg="<svg>azure</svg>"
        )


@pytest.fixture
def mock_design_tools_client(
    monkeypatch: pytest.MonkeyPatch,
) -> _FakeDesignToolsClient:
    """Replace both ``_diagram_generator`` and ``_validator`` (the same
    ``McpToolsClient`` instance) with a fake for the duration of a test."""

    fake_client = _FakeDesignToolsClient(
        SystemDesignArtifact(architecture_summary="Valid architecture.")
    )
    monkeypatch.setattr(mcp_server, "_validator", fake_client)
    monkeypatch.setattr(mcp_server, "_diagram_generator", fake_client)
    return fake_client


def test_mcp_validation_tool(
    mock_design_tools_client: _FakeDesignToolsClient,
) -> None:
    design = SystemDesignArtifact(
        architecture_summary="Valid architecture.",
        components=[
            DesignComponent(
                id="api",
                name="API",
                responsibility="Handles requests.",
            )
        ],
    )

    result = validate_system_design(design.model_dump_json())

    parsed = json.loads(result)

    assert parsed["valid"] is True
    assert len(mock_design_tools_client.validate_calls) == 1


def test_mcp_generate_diagram_tool_validates_then_renders(
    mock_design_tools_client: _FakeDesignToolsClient,
) -> None:
    design = SystemDesignArtifact(architecture_summary="Valid architecture.")

    result = mcp_server.generate_architecture_diagram(design.model_dump_json())
    parsed = json.loads(result)

    assert parsed["logical_svg"] == "<svg>logical</svg>"
    assert parsed["azure_mapping_svg"] == "<svg>azure</svg>"
    assert len(mock_design_tools_client.validate_calls) == 1
    assert len(mock_design_tools_client.generate_calls) == 1


def test_work_breakdown_schema_is_valid_json() -> None:
    result = work_breakdown_schema()

    schema = json.loads(result)

    assert "properties" in schema
    assert "features" in schema["properties"]
    assert "ambiguities" in schema["properties"]


class _FakeWorkBreakdownAgent:
    """A ``WorkBreakdownAgentPort`` fake - the work-breakdown analogue of
    ``_FakeSystemDesignAgent`` above, injected into the module-level
    ``_work_breakdown_analyzer`` singleton for the duration of a test."""

    def __init__(self, breakdown: WorkBreakdownArtifact) -> None:
        self.breakdown = breakdown
        self.calls: list[
            tuple[
                RequirementsArtifact,
                SystemDesignArtifact,
                WorkBreakdownArtifact | None,
                str | None,
            ]
        ] = []

    async def generate(
        self,
        requirements: RequirementsArtifact,
        design: SystemDesignArtifact,
        previous_breakdown: WorkBreakdownArtifact | None = None,
        refinement_input: str | None = None,
    ) -> WorkBreakdownArtifact:
        self.calls.append((requirements, design, previous_breakdown, refinement_input))
        return self.breakdown


@pytest.fixture
def mock_work_breakdown_agent() -> _FakeWorkBreakdownAgent:
    """Replace the module-level ``_work_breakdown_analyzer``'s underlying
    ``WorkBreakdownAgentPort`` with a fake for the duration of a test."""

    fake_agent = _FakeWorkBreakdownAgent(WorkBreakdownArtifact())
    mcp_server._work_breakdown_analyzer.agent = fake_agent
    return fake_agent


def test_generate_work_breakdown_tool_returns_structured_artifact(
    mock_work_breakdown_agent: _FakeWorkBreakdownAgent,
) -> None:
    requirements = _requirements_artifact("A todo app for small teams.").model_copy(
        update={
            "functional_requirements": [
                Requirement(
                    id="FR-001",
                    description="Users can create a task.",
                    priority="high",
                )
            ]
        }
    )
    design = SystemDesignArtifact(
        architecture_summary="A design.",
        components=[
            DesignComponent(id="C-001", name="API", responsibility="Serves requests.")
        ],
    )
    breakdown = WorkBreakdownArtifact()
    mock_work_breakdown_agent.breakdown = breakdown

    result = mcp_server.generate_work_breakdown(
        requirements.model_dump_json(),
        design.model_dump_json(),
    )

    parsed = WorkBreakdownArtifact.model_validate_json(result)

    assert parsed == breakdown
    assert len(mock_work_breakdown_agent.calls) == 1


def test_refine_work_breakdown_tool_passes_previous_breakdown_as_context(
    mock_work_breakdown_agent: _FakeWorkBreakdownAgent,
) -> None:
    requirements = _requirements_artifact("A todo app for small teams.").model_copy(
        update={
            "functional_requirements": [
                Requirement(
                    id="FR-001",
                    description="Users can create a task.",
                    priority="high",
                )
            ]
        }
    )
    design = SystemDesignArtifact(
        architecture_summary="A design.",
        components=[
            DesignComponent(id="C-001", name="API", responsibility="Serves requests.")
        ],
    )
    previous = WorkBreakdownArtifact()
    refined = WorkBreakdownArtifact()
    mock_work_breakdown_agent.breakdown = refined

    result = mcp_server.refine_work_breakdown(
        "Add a delete-task story.",
        requirements.model_dump_json(),
        design.model_dump_json(),
        previous.model_dump_json(),
    )

    parsed = WorkBreakdownArtifact.model_validate_json(result)

    assert parsed == refined

    [(sent_requirements, sent_design, sent_previous, sent_refinement_input)] = (
        mock_work_breakdown_agent.calls
    )
    assert sent_requirements == requirements
    assert sent_design == design
    assert sent_previous == previous
    assert sent_refinement_input == "Add a delete-task story."


class _FakeWorkBreakdownExporter:
    """A ``WorkBreakdownExporterPort`` fake standing in for
    ``McpToolsClient`` - the work-breakdown analogue of
    ``_FakeDesignToolsClient`` above."""

    def __init__(self, export: WorkBreakdownExport) -> None:
        self.export_result = export
        self.export_calls: list[
            tuple[WorkBreakdownArtifact, RequirementsArtifact, SystemDesignArtifact]
        ] = []

    def export(
        self,
        breakdown: WorkBreakdownArtifact,
        requirements: RequirementsArtifact,
        design: SystemDesignArtifact,
    ) -> WorkBreakdownExport:
        self.export_calls.append((breakdown, requirements, design))
        return self.export_result


def test_export_work_breakdown_csv_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_exporter = _FakeWorkBreakdownExporter(
        WorkBreakdownExport(csv_text="feature,story,task\r\n")
    )
    monkeypatch.setattr(mcp_server, "_work_breakdown_exporter", fake_exporter)

    requirements = _requirements_artifact("A todo app for small teams.")
    design = SystemDesignArtifact(architecture_summary="A design.")
    breakdown = WorkBreakdownArtifact()

    result = mcp_server.export_work_breakdown_csv(
        breakdown.model_dump_json(),
        requirements.model_dump_json(),
        design.model_dump_json(),
    )

    parsed = WorkBreakdownExport.model_validate_json(result)

    assert parsed.csv_text == "feature,story,task\r\n"
    assert len(fake_exporter.export_calls) == 1
