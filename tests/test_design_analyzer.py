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


def test_analyze_passes_previous_design_and_refinement_input_through() -> None:
    analyzer = SystemDesignAnalyzer.__new__(SystemDesignAnalyzer)

    previous = SystemDesignArtifact(
        architecture_summary="Original architecture.",
        components=[
            DesignComponent(
                id="CMP-001",
                name="Application",
                responsibility="Handles user interactions.",
            )
        ],
    )
    refined = SystemDesignArtifact(architecture_summary="Refined architecture.")

    response = MagicMock()
    response.output_parsed = refined

    analyzer.client = MagicMock()
    analyzer.client.responses.parse.return_value = response
    analyzer.model = "test-model"

    result = analyzer.analyze(
        create_requirements(),
        previous_design=previous,
        refinement_input="Add a notifications component.",
    )

    assert result.architecture_summary == "Refined architecture."

    sent_input = analyzer.client.responses.parse.call_args.kwargs["input"]
    sent_prompt = sent_input[1]["content"]
    assert "Original architecture." in sent_prompt
    assert "Add a notifications component." in sent_prompt


def test_prompt_forbids_interfaces_targeting_external_dependencies() -> None:
    """Regression test for a real generation failure: the model once
    produced an interface whose target was an external dependency's ID
    (e.g. "Payment Service" -> "Stripe API"), which
    ArchitectureValidator correctly rejects (interfaces are
    component-to-component only; a dependency's usage belongs in that
    dependency's own `used_by_components`) — see
    test_design_validator.py's coverage of that rule. The fix here is
    prompt-side: make the constraint explicit so the model doesn't produce
    that shape in the first place. This test guards against that
    instruction quietly being dropped in a future prompt edit.
    """
    prompt = SystemDesignAnalyzer._build_prompt(create_requirements())

    assert "used_by_components" in prompt
    assert "never as an interface" in prompt
