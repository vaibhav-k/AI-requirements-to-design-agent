"""Use case: analyze (or refine) free text into structured requirements.

Pure orchestration - no I/O of its own, no knowledge of Azure, Microsoft
Agent Framework, HTTP, or MCP. Fully testable with a fake
``RequirementsAgentPort`` (see ``tests/test_analyze_requirements_use_case
.py``), since it depends only on the ``app.application.ports`` interface,
never on a concrete infrastructure adapter.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.ports import RequirementsAgentPort
from app.domain.requirements import RequirementsArtifact


@dataclass(slots=True)
class AnalyzeRequirementsUseCase:
    """Analyze or refine requirements via an injected ``RequirementsAgentPort``."""

    agent: RequirementsAgentPort

    async def execute(
        self,
        user_input: str,
        previous_artifact: RequirementsArtifact | None = None,
    ) -> RequirementsArtifact:
        """Return a structured ``RequirementsArtifact`` for ``user_input``.

        Refines ``previous_artifact`` instead of starting fresh when one
        is given - same contract the old ``RequirementsAnalyzer.analyze``
        had, preserved here so callers migrating to this use case don't
        need to change their refinement logic.
        """

        if not user_input.strip():
            raise ValueError("user_input must not be empty.")

        return await self.agent.analyze(user_input, previous_artifact)
