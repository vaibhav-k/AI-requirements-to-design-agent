from __future__ import annotations

from unittest.mock import MagicMock

from app.analyzer import RequirementsAnalyzer
from app.models import (
    Actor,
    Requirement,
    RequirementsArtifact,
)


def create_artifact() -> RequirementsArtifact:
    """Create a representative test artifact."""

    return RequirementsArtifact(
        summary="A requirements analysis.",
        business_goal="Understand user requirements.",
        actors=[
            Actor(
                name="User",
                description="Person providing requirements.",
            )
        ],
        functional_requirements=[
            Requirement(
                id="FR-001",
                description="The system shall analyze requirements.",
                priority="high",
            )
        ],
        non_functional_requirements=[],
        data_requirements=["Requirement text"],
        integration_requirements=["OpenAI"],
        constraints=["Do not design architecture."],
        assumptions=[],
        open_questions=[],
    )


def test_analyzer_returns_structured_artifact() -> None:
    """Analyzer should return the parsed Pydantic artifact."""

    analyzer = RequirementsAnalyzer.__new__(RequirementsAnalyzer)

    analyzer.model = "test-model"
    analyzer.client = MagicMock()

    artifact = create_artifact()

    response = MagicMock()
    response.output_parsed = artifact

    analyzer.client.responses.parse.return_value = response

    result = analyzer.analyze("Build an AI requirements analyzer.")

    assert result == artifact
    assert result.functional_requirements[0].id == "FR-001"

    analyzer.client.responses.parse.assert_called_once()
