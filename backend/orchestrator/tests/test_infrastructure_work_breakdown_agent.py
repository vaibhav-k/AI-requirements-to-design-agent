from __future__ import annotations

from typing import Any

import pytest

from app.application.errors import WorkBreakdownGenerationError
from app.domain.design import DesignComponent, SystemDesignArtifact
from app.domain.requirements import Requirement, RequirementsArtifact
from app.domain.work_breakdown import WorkBreakdownArtifact, WorkBreakdownFeature
from app.infrastructure.agents.work_breakdown_agent import (
    AgentFrameworkWorkBreakdownAgent,
    _build_prompt,
    _valid_architecture_ids,
    _valid_requirement_ids,
)


def _requirements() -> RequirementsArtifact:
    return RequirementsArtifact(
        summary="Customers can manage their profile.",
        business_goal="Let customers self-serve profile updates.",
        actors=[],
        functional_requirements=[
            Requirement(id="FR-001", description="Create a customer.", priority="high")
        ],
        non_functional_requirements=[
            Requirement(
                id="NFR-001",
                description="Sub-second responses.",
                priority="medium",
            )
        ],
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


async def test_generate_returns_the_parsed_breakdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    breakdown = WorkBreakdownArtifact(
        features=[WorkBreakdownFeature(feature="Customer Management")]
    )
    fake_underlying_agent = _FakeUnderlyingAgent(response_value=breakdown)

    monkeypatch.setattr(
        "app.infrastructure.agents.work_breakdown_agent.OpenAIChatClient",
        lambda **kwargs: _FakeChatClient(fake_underlying_agent, **kwargs),
    )

    agent = AgentFrameworkWorkBreakdownAgent(**_agent_kwargs())

    result = await agent.generate(_requirements(), _design())

    assert result == breakdown
    assert len(fake_underlying_agent.run_calls) == 1


async def test_generate_raises_work_breakdown_generation_error_when_no_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_underlying_agent = _FakeUnderlyingAgent(response_value=None)

    monkeypatch.setattr(
        "app.infrastructure.agents.work_breakdown_agent.OpenAIChatClient",
        lambda **kwargs: _FakeChatClient(fake_underlying_agent, **kwargs),
    )

    agent = AgentFrameworkWorkBreakdownAgent(**_agent_kwargs())

    with pytest.raises(WorkBreakdownGenerationError):
        await agent.generate(_requirements(), _design())


async def test_generate_wraps_underlying_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RaisingAgent:
        async def run(self, prompt: str, **kwargs: Any) -> _FakeAgentResponse:
            raise RuntimeError("network exploded")

    monkeypatch.setattr(
        "app.infrastructure.agents.work_breakdown_agent.OpenAIChatClient",
        lambda **kwargs: _FakeChatClient(_RaisingAgent(), **kwargs),  # type: ignore[arg-type]
    )

    agent = AgentFrameworkWorkBreakdownAgent(**_agent_kwargs())

    with pytest.raises(WorkBreakdownGenerationError):
        await agent.generate(_requirements(), _design())


def test_valid_id_helpers_collect_every_id() -> None:
    requirements = _requirements()
    design = _design()

    assert _valid_requirement_ids(requirements) == ["FR-001", "NFR-001"]
    assert _valid_architecture_ids(design) == ["api"]


def test_prompt_lists_the_exact_valid_ids_and_forbids_fabrication() -> None:
    """Regression test: the prompt must give the model the actual
    requirement/architecture IDs from the supplied artifacts and tell it
    to use only those, rather than trusting it to avoid fabricating an ID
    on its own - see this module's docstring."""

    prompt = _build_prompt(_requirements(), _design(), None, None)

    assert "['FR-001', 'NFR-001']" in prompt
    assert "['api']" in prompt
    assert "never invent one" in prompt


def test_prompt_includes_refinement_context_when_refining() -> None:
    previous = WorkBreakdownArtifact(
        features=[WorkBreakdownFeature(feature="Customer Management")]
    )

    prompt = _build_prompt(_requirements(), _design(), previous, "Add deletion.")

    assert "refining a previously generated work breakdown" in prompt
    assert "Add deletion." in prompt
