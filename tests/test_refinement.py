from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.application.use_cases.analyze_requirements import AnalyzeRequirementsUseCase
from app.domain.requirements import (
    RequirementsArtifact,
)
from app.session import DesignSession


def create_artifact(
    summary: str,
) -> RequirementsArtifact:
    """Create a minimal requirements artifact."""

    return RequirementsArtifact(
        summary=summary,
        business_goal="Test business goal.",
        actors=[],
        functional_requirements=[],
        non_functional_requirements=[],
        data_requirements=[],
        integration_requirements=[],
        constraints=[],
        assumptions=[],
        open_questions=[],
    )


def test_refinement_passes_previous_artifact() -> None:
    """A refinement should pass the current artifact to the analyzer."""

    analyzer = MagicMock(spec=AnalyzeRequirementsUseCase)

    store = MagicMock()

    first_artifact = create_artifact("Initial analysis.")

    refined_artifact = create_artifact("Refined analysis.")

    # `DesignSession.analyze` bridges into this use case's async `execute`
    # via `run_sync` (see app/infrastructure/sync_bridge.py) — an `AsyncMock`
    # here stands in for the coroutine that bridge awaits.
    analyzer.execute = AsyncMock(
        side_effect=[
            first_artifact,
            refined_artifact,
        ]
    )

    session = DesignSession(analyzer, store)

    first_result = session.analyze("Build an AI requirements analyzer.")

    second_result = session.analyze("Also support refinement.")

    assert first_result.version == 1
    assert second_result.version == 2

    assert analyzer.execute.call_count == 2

    first_call = analyzer.execute.call_args_list[0]

    assert first_call.kwargs["previous_artifact"] is None

    second_call = analyzer.execute.call_args_list[1]

    assert second_call.kwargs["previous_artifact"] == first_artifact

    assert session.current_artifact == refined_artifact
