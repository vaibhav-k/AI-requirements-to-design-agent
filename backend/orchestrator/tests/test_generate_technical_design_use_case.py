from __future__ import annotations

import pytest

from app.application.use_cases.generate_technical_design import (
    GenerateTechnicalDesignUseCase,
)
from app.domain.design import DesignComponent, SystemDesignArtifact
from app.domain.requirements import Requirement, RequirementsArtifact
from app.domain.technical_design import DesignSection, TechnicalDesignArtifact
from app.domain.work_breakdown import (
    WorkBreakdownArtifact,
    WorkBreakdownFeature,
    WorkBreakdownStory,
    WorkBreakdownTask,
)


def _requirements() -> RequirementsArtifact:
    return RequirementsArtifact(
        summary="s",
        business_goal="g",
        actors=[],
        functional_requirements=[
            Requirement(id="FR-001", description="Do a thing.", priority="high")
        ],
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


def _work_breakdown(*, with_feature: bool = True) -> WorkBreakdownArtifact:
    return WorkBreakdownArtifact(
        features=(
            [
                WorkBreakdownFeature(
                    feature="Customer Management",
                    stories=[
                        WorkBreakdownStory(
                            story="Create customer",
                            tasks=[
                                WorkBreakdownTask(
                                    task="Implement POST /customers endpoint",
                                    description="Add the endpoint.",
                                    effort="M",
                                    requirement_ids=["FR-001"],
                                    architecture_ids=["api"],
                                )
                            ],
                        )
                    ],
                )
            ]
            if with_feature
            else []
        )
    )


def _document() -> TechnicalDesignArtifact:
    return TechnicalDesignArtifact(
        document_title="Customer Management Technical Design",
        sections=[
            DesignSection(
                title="Architecture Overview",
                level=1,
                body="The system exposes a single API component.",
                include_diagram=True,
            )
        ],
    )


class _FakePort:
    def __init__(self, document: TechnicalDesignArtifact) -> None:
        self.document = document
        self.calls: list[tuple] = []

    async def generate(
        self,
        requirements: RequirementsArtifact,
        design: SystemDesignArtifact,
        work_breakdown: WorkBreakdownArtifact,
        previous_document: TechnicalDesignArtifact | None = None,
        refinement_input: str | None = None,
    ) -> TechnicalDesignArtifact:
        self.calls.append(
            (requirements, design, work_breakdown, previous_document, refinement_input)
        )
        return self.document


async def test_execute_delegates_to_the_port() -> None:
    document = _document()
    port = _FakePort(document)
    use_case = GenerateTechnicalDesignUseCase(agent=port)
    requirements = _requirements()
    design = _design()
    work_breakdown = _work_breakdown()

    result = await use_case.execute(requirements, design, work_breakdown)

    assert result == document
    assert port.calls == [(requirements, design, work_breakdown, None, None)]


async def test_execute_forwards_previous_document_and_refinement_input() -> None:
    previous = _document()
    refined = _document()
    port = _FakePort(refined)
    use_case = GenerateTechnicalDesignUseCase(agent=port)
    requirements = _requirements()
    design = _design()
    work_breakdown = _work_breakdown()

    await use_case.execute(
        requirements,
        design,
        work_breakdown,
        previous_document=previous,
        refinement_input="Add a data retention section.",
    )

    assert port.calls == [
        (
            requirements,
            design,
            work_breakdown,
            previous,
            "Add a data retention section.",
        )
    ]


async def test_execute_rejects_design_with_no_components() -> None:
    use_case = GenerateTechnicalDesignUseCase(agent=_FakePort(_document()))

    with pytest.raises(ValueError, match="component"):
        await use_case.execute(
            _requirements(), _design(with_component=False), _work_breakdown()
        )


async def test_execute_rejects_work_breakdown_with_no_features() -> None:
    use_case = GenerateTechnicalDesignUseCase(agent=_FakePort(_document()))

    with pytest.raises(ValueError, match="feature"):
        await use_case.execute(
            _requirements(), _design(), _work_breakdown(with_feature=False)
        )
