from __future__ import annotations

from app.application.use_cases.generate_system_design import (
    GenerateSystemDesignUseCase,
)
from app.design.models import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact


def _requirements() -> RequirementsArtifact:
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


async def test_execute_delegates_to_the_port() -> None:
    design = SystemDesignArtifact(architecture_summary="A design.")
    port = _FakePort(design)
    use_case = GenerateSystemDesignUseCase(agent=port)
    requirements = _requirements()

    result = await use_case.execute(requirements)

    assert result == design
    assert port.calls == [(requirements, None, None)]


async def test_execute_forwards_previous_design_and_refinement_input() -> None:
    previous = SystemDesignArtifact(architecture_summary="Original.")
    refined = SystemDesignArtifact(architecture_summary="Refined.")
    port = _FakePort(refined)
    use_case = GenerateSystemDesignUseCase(agent=port)
    requirements = _requirements()

    await use_case.execute(
        requirements,
        previous_design=previous,
        refinement_input="Add auditing.",
    )

    assert port.calls == [(requirements, previous, "Add auditing.")]
