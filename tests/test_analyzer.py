from __future__ import annotations

from app.analyzer import RequirementsAnalyzer
from app.domain.requirements import (
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


class _FakeRequirementsAgent:
    """A ``RequirementsAgentPort`` fake — no Microsoft Agent Framework, no
    Azure credentials required, matching this project's pattern for
    testing use cases/facades behind a port (see also
    ``tests/test_analyze_requirements_use_case.py``)."""

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


def test_analyzer_returns_structured_artifact() -> None:
    """The sync facade should return the fake agent's artifact unchanged."""

    artifact = create_artifact()
    fake_agent = _FakeRequirementsAgent(artifact)
    analyzer = RequirementsAnalyzer(agent=fake_agent)

    result = analyzer.analyze("Build an AI requirements analyzer.")

    assert result == artifact
    assert result.functional_requirements[0].id == "FR-001"
    assert fake_agent.calls == [("Build an AI requirements analyzer.", None)]


async def test_analyzer_analyze_async_returns_structured_artifact() -> None:
    """The native async entry point should behave the same as the sync one."""

    artifact = create_artifact()
    fake_agent = _FakeRequirementsAgent(artifact)
    analyzer = RequirementsAnalyzer(agent=fake_agent)

    result = await analyzer.analyze_async("Build an AI requirements analyzer.")

    assert result == artifact


def test_analyzer_passes_previous_artifact_through_for_refinement() -> None:
    """Refinement calls should forward the previous artifact to the agent."""

    artifact = create_artifact()
    fake_agent = _FakeRequirementsAgent(artifact)
    analyzer = RequirementsAnalyzer(agent=fake_agent)

    analyzer.analyze("Add a login page.", previous_artifact=artifact)

    assert fake_agent.calls == [("Add a login page.", artifact)]
