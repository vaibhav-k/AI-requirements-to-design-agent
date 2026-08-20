from __future__ import annotations

from app.application.use_cases.interpret_diagram_image import (
    InterpretDiagramImageUseCase,
)
from app.domain.design import SystemDesignArtifact


class _FakePort:
    def __init__(self, design: SystemDesignArtifact) -> None:
        self.design = design
        self.calls: list[
            tuple[bytes, str, SystemDesignArtifact | None, str | None]
        ] = []

    async def interpret(
        self,
        content: bytes,
        filename: str,
        previous_design: SystemDesignArtifact | None = None,
        notes: str | None = None,
    ) -> SystemDesignArtifact:
        self.calls.append((content, filename, previous_design, notes))
        return self.design


async def test_execute_delegates_to_the_port() -> None:
    design = SystemDesignArtifact(architecture_summary="A design.")
    port = _FakePort(design)
    use_case = InterpretDiagramImageUseCase(agent=port)

    result = await use_case.execute(b"bytes", "diagram.png")

    assert result == design
    assert port.calls == [(b"bytes", "diagram.png", None, None)]


async def test_execute_forwards_previous_design_and_notes() -> None:
    previous = SystemDesignArtifact(architecture_summary="Original.")
    refined = SystemDesignArtifact(architecture_summary="Refined.")
    port = _FakePort(refined)
    use_case = InterpretDiagramImageUseCase(agent=port)

    await use_case.execute(
        b"bytes",
        "diagram.png",
        previous_design=previous,
        notes="Add a queue.",
    )

    assert port.calls == [(b"bytes", "diagram.png", previous, "Add a queue.")]
