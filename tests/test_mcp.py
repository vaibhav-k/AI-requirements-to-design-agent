import json

import pytest

from app.domain.design import (
    DesignComponent,
    SystemDesignArtifact,
)
from app.domain.requirements import RequirementsArtifact
from app.mcp import server as mcp_server
from app.mcp.server import (
    design_schema,
    requirements_schema,
    validate_system_design,
)


class _FakeRequirementsAgent:
    """A ``RequirementsAgentPort`` fake standing in for the Microsoft
    Agent Framework-backed adapter, injected into the module-level
    ``_requirements_analyzer`` singleton for the duration of a test (see
    ``mock_requirements_agent`` below) — no real Azure OpenAI call, no
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
    ``RequirementsAgentPort`` with a fake for the duration of a test — it's
    a singleton ``AnalyzeRequirementsUseCase`` constructed at import time by
    ``app.mcp.server`` (via ``app.infrastructure.composition``), so its
    ``.agent`` is patched in place rather than re-instantiating the whole
    use case."""

    fake_agent = _FakeRequirementsAgent(_requirements_artifact())
    mcp_server._requirements_analyzer.agent = fake_agent
    return fake_agent


class _FakeSystemDesignAgent:
    """A ``SystemDesignAgentPort`` fake — the design-generation analogue
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
    ``SystemDesignAgentPort`` with a fake for the duration of a test —
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


def test_mcp_validation_tool() -> None:
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
