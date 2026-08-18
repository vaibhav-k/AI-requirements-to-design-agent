from __future__ import annotations

from typing import Any

import pytest

from app.application.errors import DesignGenerationError
from app.domain.design import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact
from app.infrastructure.agents.system_design_agent import (
    AgentFrameworkSystemDesignAgent,
    _build_prompt,
)


def _requirements() -> RequirementsArtifact:
    return RequirementsArtifact(
        summary="Users upload documents and ask questions.",
        business_goal="Allow users to ask questions about uploaded documents.",
        actors=[],
        functional_requirements=[],
        non_functional_requirements=[],
        data_requirements=["Uploaded documents"],
        integration_requirements=[],
        constraints=[],
        assumptions=[],
        open_questions=[],
    )


class _FakeAgentResponse:
    def __init__(self, value: Any) -> None:
        self.value = value


class _FakeUnderlyingAgent:
    """Stands in for the ``agent_framework.Agent`` instance returned by
    ``OpenAIChatClient.as_agent`` — see
    ``tests/test_infrastructure_requirements_agent.py`` for the same
    pattern applied to the requirements agent."""

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


async def test_generate_returns_the_parsed_design(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    design = SystemDesignArtifact(architecture_summary="High-level architecture.")
    fake_underlying_agent = _FakeUnderlyingAgent(response_value=design)

    monkeypatch.setattr(
        "app.infrastructure.agents.system_design_agent.OpenAIChatClient",
        lambda **kwargs: _FakeChatClient(fake_underlying_agent, **kwargs),
    )

    agent = AgentFrameworkSystemDesignAgent(
        api_key="test-key",
        endpoint="https://example.openai.azure.com/openai/v1/",
        model="test-model",
    )

    result = await agent.generate(_requirements())

    assert result == design
    assert len(fake_underlying_agent.run_calls) == 1


async def test_generate_raises_design_generation_error_when_no_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_underlying_agent = _FakeUnderlyingAgent(response_value=None)

    monkeypatch.setattr(
        "app.infrastructure.agents.system_design_agent.OpenAIChatClient",
        lambda **kwargs: _FakeChatClient(fake_underlying_agent, **kwargs),
    )

    agent = AgentFrameworkSystemDesignAgent(
        api_key="test-key",
        endpoint="https://example.openai.azure.com/openai/v1/",
        model="test-model",
    )

    with pytest.raises(DesignGenerationError):
        await agent.generate(_requirements())


async def test_generate_wraps_underlying_failures_as_design_generation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RaisingAgent:
        async def run(self, prompt: str, **kwargs: Any) -> _FakeAgentResponse:
            raise RuntimeError("network exploded")

    monkeypatch.setattr(
        "app.infrastructure.agents.system_design_agent.OpenAIChatClient",
        lambda **kwargs: _FakeChatClient(_RaisingAgent(), **kwargs),  # type: ignore[arg-type]
    )

    agent = AgentFrameworkSystemDesignAgent(
        api_key="test-key",
        endpoint="https://example.openai.azure.com/openai/v1/",
        model="test-model",
    )

    with pytest.raises(DesignGenerationError):
        await agent.generate(_requirements())


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
    instruction quietly being dropped in a future prompt edit. Moved
    here (from tests/test_design_analyzer.py) when the prompt itself
    moved into this module as part of the Clean Architecture migration.
    """

    prompt = _build_prompt(_requirements())

    assert "used_by_components" in prompt
    assert "never as an interface" in prompt
