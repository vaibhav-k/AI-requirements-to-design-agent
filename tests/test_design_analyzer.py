from __future__ import annotations

from app.design.analyzer import SystemDesignAnalyzer
from app.design.models import DesignComponent, SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact


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


class _FakeSystemDesignAgent:
    """A ``SystemDesignAgentPort`` fake — no Microsoft Agent Framework, no
    Azure credentials required, matching this project's pattern for
    testing facades/use cases behind a port (see also
    ``tests/test_analyzer.py``)."""

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


def test_design_analyzer_returns_structured_artifact() -> None:
    design = SystemDesignArtifact(
        architecture_summary="High-level architecture.",
        components=[
            DesignComponent(
                id="CMP-001",
                name="Application",
                responsibility="Handles user interactions.",
            )
        ],
    )
    fake_agent = _FakeSystemDesignAgent(design)
    analyzer = SystemDesignAnalyzer(agent=fake_agent)

    result = analyzer.analyze(create_requirements())

    assert result.architecture_summary == "High-level architecture."
    assert len(fake_agent.calls) == 1


async def test_design_analyzer_analyze_async_returns_structured_artifact() -> None:
    design = SystemDesignArtifact(architecture_summary="High-level architecture.")
    fake_agent = _FakeSystemDesignAgent(design)
    analyzer = SystemDesignAnalyzer(agent=fake_agent)

    result = await analyzer.analyze_async(create_requirements())

    assert result == design


def test_analyze_passes_previous_design_and_refinement_input_through() -> None:
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
    fake_agent = _FakeSystemDesignAgent(refined)
    analyzer = SystemDesignAnalyzer(agent=fake_agent)

    result = analyzer.analyze(
        create_requirements(),
        previous_design=previous,
        refinement_input="Add a notifications component.",
    )

    assert result.architecture_summary == "Refined architecture."

    [(_, sent_previous, sent_refinement_input)] = fake_agent.calls
    assert sent_previous == previous
    assert sent_refinement_input == "Add a notifications component."
