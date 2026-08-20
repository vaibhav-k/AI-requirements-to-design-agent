from __future__ import annotations

from typing import Any

import pytest

from app.application.errors import DiagramInterpretationError
from app.domain.design import SystemDesignArtifact
from app.infrastructure.agents.diagram_image_interpreter_agent import (
    AgentFrameworkDiagramImageInterpreterAgent,
    _build_prompt,
)


class _FakeAgentResponse:
    def __init__(self, value: Any) -> None:
        self.value = value


class _FakeUnderlyingAgent:
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


async def test_interpret_returns_the_parsed_design(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    design = SystemDesignArtifact(architecture_summary="Redrawn architecture.")
    fake_underlying_agent = _FakeUnderlyingAgent(response_value=design)

    monkeypatch.setattr(
        "app.infrastructure.agents.diagram_image_interpreter_agent.OpenAIChatClient",
        lambda **kwargs: _FakeChatClient(fake_underlying_agent, **kwargs),
    )

    agent = AgentFrameworkDiagramImageInterpreterAgent(
        api_key="test-key",
        endpoint="https://example.openai.azure.com/openai/v1/",
        model="test-model",
    )

    result = await agent.interpret(b"fake-image-bytes", "diagram.png")

    assert result == design
    assert len(fake_underlying_agent.run_calls) == 1


async def test_interpret_raises_diagram_interpretation_error_when_no_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_underlying_agent = _FakeUnderlyingAgent(response_value=None)

    monkeypatch.setattr(
        "app.infrastructure.agents.diagram_image_interpreter_agent.OpenAIChatClient",
        lambda **kwargs: _FakeChatClient(fake_underlying_agent, **kwargs),
    )

    agent = AgentFrameworkDiagramImageInterpreterAgent(
        api_key="test-key",
        endpoint="https://example.openai.azure.com/openai/v1/",
        model="test-model",
    )

    with pytest.raises(DiagramInterpretationError):
        await agent.interpret(b"fake-image-bytes", "diagram.png")


async def test_interpret_wraps_underlying_failures_as_diagram_interpretation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RaisingAgent:
        async def run(self, messages: Any, **kwargs: Any) -> _FakeAgentResponse:
            raise RuntimeError("network exploded")

    monkeypatch.setattr(
        "app.infrastructure.agents.diagram_image_interpreter_agent.OpenAIChatClient",
        lambda **kwargs: _FakeChatClient(_RaisingAgent(), **kwargs),  # type: ignore[arg-type]
    )

    agent = AgentFrameworkDiagramImageInterpreterAgent(
        api_key="test-key",
        endpoint="https://example.openai.azure.com/openai/v1/",
        model="test-model",
    )

    with pytest.raises(DiagramInterpretationError):
        await agent.interpret(b"fake-image-bytes", "diagram.png")


def test_prompt_includes_previous_design_and_notes_when_refining() -> None:
    previous = SystemDesignArtifact(architecture_summary="Original architecture.")

    prompt = _build_prompt(previous, "Add a caching layer.")

    assert "Original architecture." in prompt
    assert "Add a caching layer." in prompt
    assert "refines a previously generated architecture" in prompt


def test_prompt_omits_refinement_context_when_no_previous_design() -> None:
    prompt = _build_prompt(None, None)

    assert "refines a previously generated architecture" not in prompt
    assert "Additional notes from the uploader" not in prompt
