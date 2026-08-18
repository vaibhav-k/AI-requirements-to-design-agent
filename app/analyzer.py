"""Backward-compatible synchronous facade over the requirements use case.

``RequirementsAnalyzer`` used to make a raw ``openai.OpenAI().responses
.parse(...)`` call directly. As of the Clean Architecture migration (see
README → "Clean Architecture Migration"), the real work happens in:

* ``app.domain.requirements`` — the ``RequirementsArtifact`` entity
* ``app.application.ports.RequirementsAgentPort`` — the abstraction
* ``app.application.use_cases.analyze_requirements
  .AnalyzeRequirementsUseCase`` — the orchestration
* ``app.infrastructure.agents.requirements_agent
  .AgentFrameworkRequirementsAgent`` — the concrete adapter, now backed
  by Microsoft Agent Framework instead of a direct OpenAI SDK call

This class exists only so the many existing synchronous call sites
(``app/main.py``, ``app/session.py``, ``app/api/dependencies.py``,
``app/api/routes/requirements.py``, ``app/mcp/server.py``) don't all
need to change in the same slice — it's a "strangler fig" seam: those
call sites will move to constructing/injecting the use case directly in
a later slice, at which point this module can be deleted. New code
should depend on ``AnalyzeRequirementsUseCase`` + ``RequirementsAgentPort``
directly rather than adding new usages of this facade.
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

from app.application.ports import RequirementsAgentPort
from app.application.use_cases.analyze_requirements import (
    AnalyzeRequirementsUseCase,
)
from app.domain.requirements import RequirementsArtifact
from app.infrastructure.agents.requirements_agent import (
    AgentFrameworkRequirementsAgent,
)

load_dotenv()


def require_environment_variable(
    name: str,
    value: str | None,
) -> str:
    """Return a required environment variable."""

    if not value:
        raise RuntimeError(f"{name} environment variable is required.")

    return value


AZURE_OPENAI_API_KEY = require_environment_variable(
    "AZURE_OPENAI_API_KEY",
    os.getenv("AZURE_OPENAI_API_KEY"),
)

AZURE_OPENAI_ENDPOINT = require_environment_variable(
    "AZURE_OPENAI_ENDPOINT",
    os.getenv("AZURE_OPENAI_ENDPOINT"),
)

AZURE_OPENAI_MODEL = require_environment_variable(
    "AZURE_OPENAI_MODEL",
    os.getenv("AZURE_OPENAI_MODEL"),
)


class RequirementsAnalyzer:
    """Analyze user input into structured requirements (sync facade)."""

    def __init__(
        self,
        model: str = AZURE_OPENAI_MODEL,
        agent: RequirementsAgentPort | None = None,
    ) -> None:
        """``agent`` is injectable — pass a fake/mock ``RequirementsAgentPort``
        in tests instead of constructing a real Microsoft Agent Framework
        agent (and therefore requiring live Azure OpenAI credentials)."""

        resolved_agent: RequirementsAgentPort = agent or (
            AgentFrameworkRequirementsAgent(
                api_key=AZURE_OPENAI_API_KEY,
                endpoint=AZURE_OPENAI_ENDPOINT,
                model=model,
            )
        )

        self._use_case = AnalyzeRequirementsUseCase(agent=resolved_agent)

    async def analyze_async(
        self,
        user_input: str,
        previous_artifact: RequirementsArtifact | None = None,
    ) -> RequirementsArtifact:
        """Analyze requirements and return a structured artifact.

        The native, non-bridged entry point — use this from any ``async
        def`` caller (e.g. ``start_run_from_upload``/``refine_run_from_upload``
        in ``app/api/routes/requirements.py``) instead of ``analyze()``,
        which cannot be called from inside a running event loop.
        """

        return await self._use_case.execute(user_input, previous_artifact)

    def analyze(
        self,
        user_input: str,
        previous_artifact: RequirementsArtifact | None = None,
    ) -> RequirementsArtifact:
        """Synchronous wrapper around ``analyze_async``, for callers that
        aren't themselves ``async`` — the CLI (``app/main.py``,
        ``app/session.py``), the sync FastAPI routes (``start_run``/
        ``refine_run``, which FastAPI runs in a worker thread with no
        event loop of its own), and the MCP tool functions
        (``app/mcp/server.py``).

        Raises ``RuntimeError`` if called from inside a *running* event
        loop (i.e. from an ``async def`` function) — ``asyncio.run``
        cannot nest inside one; call ``analyze_async`` directly instead.
        """

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "RequirementsAnalyzer.analyze() cannot be called from a "
                "running event loop — await analyze_async() instead."
            )

        return asyncio.run(self._use_case.execute(user_input, previous_artifact))
