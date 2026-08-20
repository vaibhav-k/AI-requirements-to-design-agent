from __future__ import annotations

from typing import Any

import pytest

from app.application.errors import ImageClassificationError
from app.domain.vision import ImageClassification
from app.infrastructure.agents.image_classifier_agent import (
    AgentFrameworkImageClassifierAgent,
)


class _FakeAgentResponse:
    def __init__(self, value: Any) -> None:
        self.value = value


class _FakeUnderlyingAgent:
    """Stands in for the ``agent_framework.Agent`` instance returned by
    ``OpenAIChatClient.as_agent`` - see
    ``tests/test_infrastructure_requirements_agent.py`` for the same
    pattern applied to the requirements agent."""

    def __init__(self, response_value: Any) -> None:
        self.response_value = response_value
        self.run_calls: list[tuple[Any, dict[str, Any]]] = []

    async def run(self, messages: Any, **kwargs: Any) -> _FakeAgentResponse:
        self.run_calls.append((messages, kwargs))
        return _FakeAgentResponse(self.response_value)


class _FakeChatClient:
    def __init__(self, agent: _FakeUnderlyingAgent, **kwargs: Any) -> None:
        self.init_kwargs = kwargs
        self._agent = agent

    def as_agent(self, **kwargs: Any) -> _FakeUnderlyingAgent:
        self.as_agent_kwargs = kwargs
        return self._agent


async def test_classify_returns_the_parsed_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    classification = ImageClassification(kind="diagram", reasoning="Boxes and arrows.")
    fake_underlying_agent = _FakeUnderlyingAgent(response_value=classification)

    monkeypatch.setattr(
        "app.infrastructure.agents.image_classifier_agent.OpenAIChatClient",
        lambda **kwargs: _FakeChatClient(fake_underlying_agent, **kwargs),
    )

    agent = AgentFrameworkImageClassifierAgent(
        api_key="test-key",
        endpoint="https://example.openai.azure.com/openai/v1/",
        model="test-model",
    )

    result = await agent.classify(b"fake-image-bytes", "diagram.png")

    assert result == classification
    assert len(fake_underlying_agent.run_calls) == 1


async def test_classify_raises_image_classification_error_when_no_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_underlying_agent = _FakeUnderlyingAgent(response_value=None)

    monkeypatch.setattr(
        "app.infrastructure.agents.image_classifier_agent.OpenAIChatClient",
        lambda **kwargs: _FakeChatClient(fake_underlying_agent, **kwargs),
    )

    agent = AgentFrameworkImageClassifierAgent(
        api_key="test-key",
        endpoint="https://example.openai.azure.com/openai/v1/",
        model="test-model",
    )

    with pytest.raises(ImageClassificationError):
        await agent.classify(b"fake-image-bytes", "diagram.png")


async def test_classify_wraps_underlying_failures_as_image_classification_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RaisingAgent:
        async def run(self, messages: Any, **kwargs: Any) -> _FakeAgentResponse:
            raise RuntimeError("network exploded")

    monkeypatch.setattr(
        "app.infrastructure.agents.image_classifier_agent.OpenAIChatClient",
        lambda **kwargs: _FakeChatClient(_RaisingAgent(), **kwargs),  # type: ignore[arg-type]
    )

    agent = AgentFrameworkImageClassifierAgent(
        api_key="test-key",
        endpoint="https://example.openai.azure.com/openai/v1/",
        model="test-model",
    )

    with pytest.raises(ImageClassificationError):
        await agent.classify(b"fake-image-bytes", "diagram.png")
