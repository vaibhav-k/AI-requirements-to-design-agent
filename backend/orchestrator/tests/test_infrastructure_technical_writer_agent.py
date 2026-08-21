from __future__ import annotations

from typing import Any

import pytest

from app.application.errors import TechnicalDesignGenerationError
from app.domain.design import DesignComponent, SystemDesignArtifact
from app.domain.requirements import Requirement, RequirementsArtifact
from app.domain.technical_design import DesignSection, TechnicalDesignArtifact
from app.domain.work_breakdown import (
    WorkBreakdownArtifact,
    WorkBreakdownFeature,
    WorkBreakdownStory,
    WorkBreakdownTask,
)
from app.infrastructure.agents.technical_writer_agent import (
    AgentFrameworkTechnicalWriterAgent,
    _build_prompt,
)


def _requirements() -> RequirementsArtifact:
    return RequirementsArtifact(
        summary="Customers can manage their profile.",
        business_goal="Let customers self-serve profile updates.",
        actors=[],
        functional_requirements=[
            Requirement(id="FR-001", description="Create a customer.", priority="high")
        ],
        non_functional_requirements=[],
        data_requirements=[],
        integration_requirements=[],
        constraints=[],
        assumptions=[],
        open_questions=[],
    )


def _design() -> SystemDesignArtifact:
    return SystemDesignArtifact(
        architecture_summary="A simple API + database design.",
        components=[
            DesignComponent(
                id="api",
                name="API",
                responsibility="Handles requests.",
                requirement_ids=["FR-001"],
            )
        ],
    )


def _work_breakdown() -> WorkBreakdownArtifact:
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


class _FakeAgentResponse:
    def __init__(self, value: Any) -> None:
        self.value = value


class _FakeUnderlyingAgent:
    def __init__(self, response_value: Any) -> None:
        self.response_value = response_value
        self.run_calls: list[tuple[str, dict[str, Any]]] = []

    async def run(self, prompt: str, **kwargs: Any) -> _FakeAgentResponse:
        self.run_calls.append((prompt, kwargs))
        return _FakeAgentResponse(self.response_value)


class _FakeChatClient:
    def __init__(self, agent: _FakeUnderlyingAgent, **kwargs: Any) -> None:
        self.init_kwargs = kwargs
        self._agent = agent

    def as_agent(self, **kwargs: Any) -> _FakeUnderlyingAgent:
        self.as_agent_kwargs = kwargs
        return self._agent


def _agent_kwargs() -> dict[str, str]:
    return {
        "api_key": "test-key",
        "endpoint": "https://example.openai.azure.com/openai/v1/",
        "model": "test-model",
    }


async def test_generate_returns_the_parsed_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document()
    fake_underlying_agent = _FakeUnderlyingAgent(response_value=document)

    monkeypatch.setattr(
        "app.infrastructure.agents.technical_writer_agent.OpenAIChatClient",
        lambda **kwargs: _FakeChatClient(fake_underlying_agent, **kwargs),
    )

    agent = AgentFrameworkTechnicalWriterAgent(**_agent_kwargs())

    result = await agent.generate(_requirements(), _design(), _work_breakdown())

    assert result == document
    assert len(fake_underlying_agent.run_calls) == 1


async def test_generate_raises_technical_design_generation_error_when_no_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_underlying_agent = _FakeUnderlyingAgent(response_value=None)

    monkeypatch.setattr(
        "app.infrastructure.agents.technical_writer_agent.OpenAIChatClient",
        lambda **kwargs: _FakeChatClient(fake_underlying_agent, **kwargs),
    )

    agent = AgentFrameworkTechnicalWriterAgent(**_agent_kwargs())

    with pytest.raises(TechnicalDesignGenerationError):
        await agent.generate(_requirements(), _design(), _work_breakdown())


async def test_generate_wraps_underlying_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RaisingAgent:
        async def run(self, prompt: str, **kwargs: Any) -> _FakeAgentResponse:
            raise RuntimeError("network exploded")

    monkeypatch.setattr(
        "app.infrastructure.agents.technical_writer_agent.OpenAIChatClient",
        lambda **kwargs: _FakeChatClient(_RaisingAgent(), **kwargs),  # type: ignore[arg-type]
    )

    agent = AgentFrameworkTechnicalWriterAgent(**_agent_kwargs())

    with pytest.raises(TechnicalDesignGenerationError):
        await agent.generate(_requirements(), _design(), _work_breakdown())


def test_prompt_includes_every_upstream_artifact() -> None:
    prompt = _build_prompt(_requirements(), _design(), _work_breakdown(), None, None)

    assert "FR-001" in prompt
    assert '"id": "api"' in prompt
    assert "Customer Management" in prompt


def test_prompt_includes_refinement_context_when_refining() -> None:
    previous = _document()

    prompt = _build_prompt(
        _requirements(),
        _design(),
        _work_breakdown(),
        previous,
        "Add a data retention section.",
    )

    assert "refining a previously generated technical design document" in prompt
    assert "Add a data retention section." in prompt
