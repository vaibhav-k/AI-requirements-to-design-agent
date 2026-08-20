"""Use case: generate (or refine) a Feature -> Story -> Task work breakdown.

Same shape as ``generate_system_design.py``'s
``GenerateSystemDesignUseCase`` - pure orchestration against a port, no
knowledge of Azure, Microsoft Agent Framework, HTTP, or MCP.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.ports import WorkBreakdownAgentPort
from app.domain.design import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact
from app.domain.work_breakdown import WorkBreakdownArtifact


@dataclass(slots=True)
class GenerateWorkBreakdownUseCase:
    """Generate or refine a work breakdown via an injected
    ``WorkBreakdownAgentPort``."""

    agent: WorkBreakdownAgentPort

    async def execute(
        self,
        requirements: RequirementsArtifact,
        design: SystemDesignArtifact,
        previous_breakdown: WorkBreakdownArtifact | None = None,
        refinement_input: str | None = None,
    ) -> WorkBreakdownArtifact:
        """Return a structured ``WorkBreakdownArtifact`` for
        ``requirements``/``design``.

        Refines ``previous_breakdown`` (guided by ``refinement_input``)
        instead of generating one from scratch when ``previous_breakdown``
        is given. Requires at least one functional or non-functional
        requirement and at least one architecture component - a work
        breakdown has nothing to trace back to otherwise. Failures surface
        as ``app.application.errors.WorkBreakdownGenerationError``, raised
        by the port implementation.
        """

        has_requirements = (
            requirements.functional_requirements
            or requirements.non_functional_requirements
        )
        if not has_requirements:
            raise ValueError(
                "requirements must include at least one functional or "
                "non-functional requirement."
            )

        if not design.components:
            raise ValueError("design must include at least one component.")

        return await self.agent.generate(
            requirements,
            design,
            previous_breakdown=previous_breakdown,
            refinement_input=refinement_input,
        )
