"""Use case: generate (or refine) a high-level system design.

Same shape as ``analyze_requirements.py``'s ``AnalyzeRequirementsUseCase``
— pure orchestration against a port, no knowledge of Azure, Microsoft
Agent Framework, HTTP, or MCP.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.ports import SystemDesignAgentPort
from app.design.models import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact


@dataclass(slots=True)
class GenerateSystemDesignUseCase:
    """Generate or refine a system design via an injected ``SystemDesignAgentPort``."""

    agent: SystemDesignAgentPort

    async def execute(
        self,
        requirements: RequirementsArtifact,
        previous_design: SystemDesignArtifact | None = None,
        refinement_input: str | None = None,
    ) -> SystemDesignArtifact:
        """Return a structured ``SystemDesignArtifact`` for ``requirements``.

        Refines ``previous_design`` (guided by ``refinement_input``)
        instead of generating one from scratch when ``previous_design``
        is given — same contract the old ``SystemDesignAnalyzer.analyze``
        had. Failures surface as ``app.application.errors
        .DesignGenerationError``, raised by the port implementation.
        """

        return await self.agent.generate(
            requirements,
            previous_design=previous_design,
            refinement_input=refinement_input,
        )
