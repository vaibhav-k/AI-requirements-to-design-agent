import json
from unittest.mock import MagicMock

import pytest

from app.design.models import (
    DesignComponent,
    SystemDesignArtifact,
)
from app.mcp import server as mcp_server
from app.mcp.server import (
    design_schema,
    requirements_schema,
    validate_system_design,
)
from app.models import RequirementsArtifact


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
def mock_requirements_client() -> MagicMock:
    """Replace the module-level `_requirements_analyzer`'s OpenAI client
    with a mock for the duration of a test, the same way test_analyzer.py
    mocks a standalone RequirementsAnalyzer — this one is a singleton
    constructed at import time by app.mcp.server, so it's patched in place
    rather than re-instantiated."""

    client = MagicMock()
    mcp_server._requirements_analyzer.client = client
    return client


@pytest.fixture
def mock_design_client() -> MagicMock:
    """Replace the module-level `_design_analyzer`'s OpenAI client with a
    mock, the same way `mock_requirements_client` does for the requirements
    analyzer singleton."""

    client = MagicMock()
    mcp_server._design_analyzer.client = client
    return client


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
    mock_requirements_client: MagicMock,
) -> None:
    artifact = _requirements_artifact("A todo app for small teams.")

    response = MagicMock()
    response.output_parsed = artifact
    mock_requirements_client.responses.parse.return_value = response

    result = mcp_server.analyze_requirements("Build a todo app for small teams.")

    parsed = RequirementsArtifact.model_validate_json(result)

    assert parsed == artifact
    assert mock_requirements_client.responses.parse.call_count == 1


def test_refine_requirements_tool_passes_previous_artifact_as_context(
    mock_requirements_client: MagicMock,
) -> None:
    previous = _requirements_artifact("Initial analysis.")
    refined = _requirements_artifact("Refined analysis.")

    response = MagicMock()
    response.output_parsed = refined
    mock_requirements_client.responses.parse.return_value = response

    result = mcp_server.refine_requirements(
        "Also support due dates.",
        previous.model_dump_json(),
    )

    parsed = RequirementsArtifact.model_validate_json(result)

    assert parsed == refined

    # The analyzer builds its prompt from `previous_artifact` — confirm the
    # previous artifact's own summary made it into the prompt sent to the
    # model, i.e. refine_requirements actually threaded `previous` through
    # rather than analyzing `user_input` in isolation.
    sent_input = mock_requirements_client.responses.parse.call_args.kwargs["input"]
    sent_prompt = sent_input[1]["content"]
    assert "Initial analysis." in sent_prompt


def test_refine_architecture_tool_passes_previous_design_as_context(
    mock_design_client: MagicMock,
) -> None:
    requirements = _requirements_artifact("A todo app for small teams.")
    previous_design = SystemDesignArtifact(
        architecture_summary="Original architecture."
    )
    refined_design = SystemDesignArtifact(architecture_summary="Refined architecture.")

    response = MagicMock()
    response.output_parsed = refined_design
    mock_design_client.responses.parse.return_value = response

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
    sent_input = mock_design_client.responses.parse.call_args.kwargs["input"]
    sent_prompt = sent_input[1]["content"]
    assert "Original architecture." in sent_prompt
    assert "Add a notifications component." in sent_prompt


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
