from __future__ import annotations

import pytest

from app.application.use_cases.generate_work_breakdown import (
    GenerateWorkBreakdownUseCase,
)
from app.domain.design import DesignComponent, SystemDesignArtifact
from app.domain.requirements import Requirement, RequirementsArtifact
from app.domain.work_breakdown import (
    WorkBreakdownArtifact,
    WorkBreakdownFeature,
    WorkBreakdownStory,
    WorkBreakdownTask,
)


def _requirements(*, with_functional: bool = True) -> RequirementsArtifact:
    return RequirementsArtifact(
        summary="s",
        business_goal="g",
        actors=[],
        functional_requirements=(
            [Requirement(id="FR-001", description="Do a thing.", priority="high")]
            if with_functional
            else []
        ),
        non_functional_requirements=[],
        data_requirements=[],
        integration_requirements=[],
        constraints=[],
        assumptions=[],
        open_questions=[],
    )


def _design(*, with_component: bool = True) -> SystemDesignArtifact:
    return SystemDesignArtifact(
        architecture_summary="A design.",
        components=(
            [
                DesignComponent(
                    id="api",
                    name="API",
                    responsibility="Handles requests.",
                    requirement_ids=["FR-001"],
                )
            ]
            if with_component
            else []
        ),
    )


def _breakdown() -> WorkBreakdownArtifact:
    return WorkBreakdownArtifact(
        features=[
            WorkBreakdownFeature(
                feature="Customer Management",
                stories=[
                    WorkBreakdownStory(
                        story="Create customer",
                        tasks=[
                            WorkBreakdownTask(
                                task="Implement POST /customers endpoint",
                                description="Add the endpoint and validation.",
                                effort="M",
                                requirement_ids=["FR-001"],
                                architecture_ids=["api"],
                            )
                        ],
                    )
                ],
            )
        ]
    )


class _FakePort:
    def __init__(self, breakdown: WorkBreakdownArtifact) -> None:
        self.breakdown = breakdown
        self.calls: list[tuple] = []

    async def generate(
        self,
        requirements: RequirementsArtifact,
        design: SystemDesignArtifact,
        previous_breakdown: WorkBreakdownArtifact | None = None,
        refinement_input: str | None = None,
    ) -> WorkBreakdownArtifact:
        self.calls.append((requirements, design, previous_breakdown, refinement_input))
        return self.breakdown


async def test_execute_delegates_to_the_port() -> None:
    breakdown = _breakdown()
    port = _FakePort(breakdown)
    use_case = GenerateWorkBreakdownUseCase(agent=port)
    requirements = _requirements()
    design = _design()

    result = await use_case.execute(requirements, design)

    assert result == breakdown
    assert port.calls == [(requirements, design, None, None)]


async def test_execute_forwards_previous_breakdown_and_refinement_input() -> None:
    previous = _breakdown()
    refined = _breakdown()
    port = _FakePort(refined)
    use_case = GenerateWorkBreakdownUseCase(agent=port)
    requirements = _requirements()
    design = _design()

    await use_case.execute(
        requirements,
        design,
        previous_breakdown=previous,
        refinement_input="Add a delete-customer story.",
    )

    assert port.calls == [
        (requirements, design, previous, "Add a delete-customer story.")
    ]


async def test_execute_rejects_requirements_with_no_requirements() -> None:
    use_case = GenerateWorkBreakdownUseCase(agent=_FakePort(_breakdown()))

    with pytest.raises(ValueError, match="requirement"):
        await use_case.execute(_requirements(with_functional=False), _design())


async def test_execute_rejects_design_with_no_components() -> None:
    use_case = GenerateWorkBreakdownUseCase(agent=_FakePort(_breakdown()))

    with pytest.raises(ValueError, match="component"):
        await use_case.execute(_requirements(), _design(with_component=False))
