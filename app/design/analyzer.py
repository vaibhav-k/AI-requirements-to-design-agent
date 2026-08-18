"""Backward-compatible synchronous facade over the design use case.

``SystemDesignAnalyzer`` used to make a raw ``openai.OpenAI().responses
.parse(...)`` call directly. As of this slice of the Clean Architecture
migration (see README → "Clean Architecture Migration"), the real work
happens in:

* ``app.design.models`` — the ``SystemDesignArtifact`` entity (not yet
  moved into ``app.domain`` — see the README section above)
* ``app.application.ports.SystemDesignAgentPort`` — the abstraction
* ``app.application.use_cases.generate_system_design
  .GenerateSystemDesignUseCase`` — the orchestration
* ``app.infrastructure.agents.system_design_agent
  .AgentFrameworkSystemDesignAgent`` — the concrete adapter, now backed
  by Microsoft Agent Framework instead of a direct OpenAI SDK call

This class exists only so the many existing synchronous call sites
(``app/main.py``, ``app/design/session.py``, ``app/api/dependencies.py``,
``app/mcp/server.py``) don't all need to change in the same slice — the
same "strangler fig" seam ``app/analyzer.py`` uses for requirements
analysis. New code should depend on ``GenerateSystemDesignUseCase`` +
``SystemDesignAgentPort`` directly rather than adding new usages of this
facade.
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

from app.application.errors import DesignGenerationError
from app.application.ports import SystemDesignAgentPort
from app.application.use_cases.generate_system_design import (
    GenerateSystemDesignUseCase,
)
from app.design.models import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact
from app.infrastructure.agents.system_design_agent import (
    AgentFrameworkSystemDesignAgent,
)

load_dotenv()

__all__ = ["DesignGenerationError", "SystemDesignAnalyzer"]


def _required_environment_variable(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"{name} environment variable is required.")

    return value


AZURE_OPENAI_API_KEY = _required_environment_variable("AZURE_OPENAI_API_KEY")

AZURE_OPENAI_ENDPOINT = _required_environment_variable("AZURE_OPENAI_ENDPOINT")

AZURE_OPENAI_MODEL = _required_environment_variable("AZURE_OPENAI_MODEL")


class SystemDesignAnalyzer:
    """Generate a high-level architecture from requirements (sync facade)."""

    def __init__(
        self,
        model: str = AZURE_OPENAI_MODEL,
        agent: SystemDesignAgentPort | None = None,
    ) -> None:
        """``agent`` is injectable — pass a fake/mock ``SystemDesignAgentPort``
        in tests instead of constructing a real Microsoft Agent Framework
        agent (and therefore requiring live Azure OpenAI credentials)."""

        resolved_agent: SystemDesignAgentPort = agent or (
            AgentFrameworkSystemDesignAgent(
                api_key=AZURE_OPENAI_API_KEY,
                endpoint=AZURE_OPENAI_ENDPOINT,
                model=model,
            )
        )

        self._use_case = GenerateSystemDesignUseCase(agent=resolved_agent)

    async def analyze_async(
        self,
        requirements: RequirementsArtifact,
        previous_design: SystemDesignArtifact | None = None,
        refinement_input: str | None = None,
    ) -> SystemDesignArtifact:
        """The native, non-bridged entry point — use this from any ``async
        def`` caller instead of ``analyze()``, which cannot be called
        from inside a running event loop. No current call site needs
        this yet (every ``ArchitectureSession.generate`` caller is sync),
        but it's kept symmetric with ``RequirementsAnalyzer.analyze_async``
        for when one does."""

        return await self._use_case.execute(
            requirements,
            previous_design=previous_design,
            refinement_input=refinement_input,
        )

    def analyze(
        self,
        requirements: RequirementsArtifact,
        previous_design: SystemDesignArtifact | None = None,
        refinement_input: str | None = None,
    ) -> SystemDesignArtifact:
        """Generate a high-level system design.

        Passing ``previous_design`` (with an accompanying
        ``refinement_input`` describing the requested change) refines that
        design instead of generating a fresh one from scratch — the
        architecture analogue of ``RequirementsAnalyzer.analyze``'s own
        ``previous_artifact`` parameter.

        Synchronous on purpose — see ``RequirementsAnalyzer.analyze``'s
        docstring for why, and why this raises ``RuntimeError`` instead
        of deadlocking/crashing confusingly if called from a running
        event loop.
        """

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "SystemDesignAnalyzer.analyze() cannot be called from a "
                "running event loop — await analyze_async() instead."
            )

        return asyncio.run(
            self._use_case.execute(
                requirements,
                previous_design=previous_design,
                refinement_input=refinement_input,
            )
        )
