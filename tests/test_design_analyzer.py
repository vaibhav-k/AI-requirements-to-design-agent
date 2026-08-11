from unittest.mock import MagicMock

from app.design.analyzer import SystemDesignAnalyzer
from app.design.models import (
    DesignComponent,
    SystemDesignArtifact,
)
from app.models import RequirementsArtifact


def create_requirements() -> RequirementsArtifact:
    return RequirementsArtifact(
        summary="Users upload documents and ask questions.",
        business_goal=("Allow users to ask questions about uploaded documents."),
        actors=[],
        functional_requirements=[],
        non_functional_requirements=[],
        data_requirements=["Uploaded documents"],
        integration_requirements=[],
        constraints=[],
        assumptions=[],
        open_questions=[],
    )


def test_design_analyzer_returns_structured_artifact() -> None:
    analyzer = SystemDesignAnalyzer.__new__(SystemDesignAnalyzer)

    parsed = SystemDesignArtifact(
        architecture_summary="High-level architecture.",
        components=[
            DesignComponent(
                id="CMP-001",
                name="Application",
                responsibility="Handles user interactions.",
            )
        ],
    )

    response = MagicMock()
    response.output_parsed = parsed

    analyzer.client = MagicMock()
    analyzer.client.responses.parse.return_value = response
    analyzer.model = "test-model"

    result = analyzer.analyze(create_requirements())

    assert result.architecture_summary == ("High-level architecture.")

    analyzer.client.responses.parse.assert_called_once()
