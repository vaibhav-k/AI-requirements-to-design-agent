"""Use case: generate (or refine) a technical design document.

Same shape as ``generate_work_breakdown.py``'s
``GenerateWorkBreakdownUseCase`` - pure orchestration against a port, no
knowledge of Azure, Microsoft Agent Framework, HTTP, or MCP.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.ports import TechnicalWriterAgentPort
from app.domain.design import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact
from app.domain.technical_design import TechnicalDesignArtifact
from app.domain.work_breakdown import WorkBreakdownArtifact


@dataclass(slots=True)
class GenerateTechnicalDesignUseCase:
    """Generate or refine a technical design document via an injected
    ``TechnicalWriterAgentPort``."""

    agent: TechnicalWriterAgentPort

    async def execute(
        self,
        requirements: RequirementsArtifact,
        design: SystemDesignArtifact,
        work_breakdown: WorkBreakdownArtifact,
        previous_document: TechnicalDesignArtifact | None = None,
        refinement_input: str | None = None,
    ) -> TechnicalDesignArtifact:
        """Return a structured ``TechnicalDesignArtifact`` compiled from
        ``requirements``/``design``/``work_breakdown``.

        Refines ``previous_document`` (guided by ``refinement_input``)
        instead of generating one from scratch when ``previous_document``
        is given. Requires at least one architecture component and at
        least one work-breakdown feature - a technical design document has
        nothing to describe otherwise. Failures surface as
        ``app.application.errors.TechnicalDesignGenerationError``, raised
        by the port implementation.
        """

        if not design.components:
            raise ValueError("design must include at least one component.")

        if not work_breakdown.features:
            raise ValueError("work breakdown must include at least one feature.")

        return await self.agent.generate(
            requirements,
            design,
            work_breakdown,
            previous_document=previous_document,
            refinement_input=refinement_input,
        )
