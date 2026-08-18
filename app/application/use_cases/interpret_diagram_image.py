"""Derive a structured system design directly from a diagram image."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.ports import DiagramImageInterpreterPort
from app.design.models import SystemDesignArtifact


@dataclass(slots=True)
class InterpretDiagramImageUseCase:
    """Thin orchestration wrapper around a ``DiagramImageInterpreterPort``
    — the diagram-image analogue of ``GenerateSystemDesignUseCase``."""

    agent: DiagramImageInterpreterPort

    async def execute(
        self,
        content: bytes,
        filename: str,
        previous_design: SystemDesignArtifact | None = None,
        notes: str | None = None,
    ) -> SystemDesignArtifact:
        return await self.agent.interpret(
            content,
            filename,
            previous_design=previous_design,
            notes=notes,
        )
