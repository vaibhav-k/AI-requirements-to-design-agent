from __future__ import annotations

import pytest

from app.application.use_cases.analyze_requirements import (
    AnalyzeRequirementsUseCase,
)
from app.domain.requirements import RequirementsArtifact


def _artifact() -> RequirementsArtifact:
    return RequirementsArtifact(
        summary="s",
        business_goal="g",
        actors=[],
        functional_requirements=[],
        non_functional_requirements=[],
        data_requirements=[],
        integration_requirements=[],
        constraints=[],
        assumptions=[],
        open_questions=[],
    )


class _FakePort:
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


async def test_execute_delegates_to_the_port() -> None:
    artifact = _artifact()
    port = _FakePort(artifact)
    use_case = AnalyzeRequirementsUseCase(agent=port)

    result = await use_case.execute("Build a thing.")

    assert result == artifact
    assert port.calls == [("Build a thing.", None)]


async def test_execute_forwards_previous_artifact() -> None:
    artifact = _artifact()
    port = _FakePort(artifact)
    use_case = AnalyzeRequirementsUseCase(agent=port)

    await use_case.execute("Refine it.", previous_artifact=artifact)

    assert port.calls == [("Refine it.", artifact)]


async def test_execute_rejects_blank_input_without_calling_the_port() -> None:
    """A pure orchestration guard — no I/O, no port call, for input that
    can never produce a meaningful analysis."""

    port = _FakePort(_artifact())
    use_case = AnalyzeRequirementsUseCase(agent=port)

    with pytest.raises(ValueError):
        await use_case.execute("   ")

    assert port.calls == []
