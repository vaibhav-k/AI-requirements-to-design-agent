from __future__ import annotations

from typing import Any

import pytest

from app.domain.requirements import RequirementsArtifact
from app.infrastructure.agents.requirements_agent import (
    AgentFrameworkRequirementsAgent,
)


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


class _FakeAgentResponse:
    def __init__(self, value: Any) -> None:
        self.value = value


class _FakeUnderlyingAgent:
    """Stands in for the ``agent_framework.Agent`` instance returned by
    ``OpenAIChatClient.as_agent`` - this test exercises
    ``AgentFrameworkRequirementsAgent`` without making any real network
    call or requiring live Azure OpenAI credentials."""

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


async def test_analyze_returns_the_parsed_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = _artifact()
    fake_underlying_agent = _FakeUnderlyingAgent(response_value=artifact)
    fake_client_instances: list[_FakeChatClient] = []

    def _fake_client_factory(**kwargs: Any) -> _FakeChatClient:
        client = _FakeChatClient(fake_underlying_agent, **kwargs)
        fake_client_instances.append(client)
        return client

    monkeypatch.setattr(
        "app.infrastructure.agents.requirements_agent.OpenAIChatClient",
        _fake_client_factory,
    )

    agent = AgentFrameworkRequirementsAgent(
        api_key="test-key",
        endpoint="https://example.openai.azure.com/openai/v1/",
        model="test-model",
    )

    result = await agent.analyze("Build a thing.")

    assert result == artifact
    assert len(fake_underlying_agent.run_calls) == 1
    assert fake_client_instances[0].init_kwargs["api_key"] == "test-key"
    assert fake_client_instances[0].init_kwargs["model"] == "test-model"


async def test_analyze_raises_when_the_agent_returns_no_parsed_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_underlying_agent = _FakeUnderlyingAgent(response_value=None)

    monkeypatch.setattr(
        "app.infrastructure.agents.requirements_agent.OpenAIChatClient",
        lambda **kwargs: _FakeChatClient(fake_underlying_agent, **kwargs),
    )

    agent = AgentFrameworkRequirementsAgent(
        api_key="test-key",
        endpoint="https://example.openai.azure.com/openai/v1/",
        model="test-model",
    )

    with pytest.raises(RuntimeError):
        await agent.analyze("Build a thing.")
