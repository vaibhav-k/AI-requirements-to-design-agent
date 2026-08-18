from __future__ import annotations

import pytest

from app.design.models import SystemDesignArtifact
from app.domain.vision import ImageClassification
from app.vision import DiagramImageInterpreter, ImageInputClassifier


class _FakeImageClassifierAgent:
    """An ``ImageClassifierPort`` fake — no Microsoft Agent Framework, no
    Azure credentials required, matching this project's pattern for
    testing facades behind a port (see also ``tests/test_analyzer.py``,
    ``tests/test_design_analyzer.py``)."""

    def __init__(self, classification: ImageClassification) -> None:
        self.classification = classification
        self.calls: list[tuple[bytes, str]] = []

    async def classify(self, content: bytes, filename: str) -> ImageClassification:
        self.calls.append((content, filename))
        return self.classification


class _FakeDiagramImageInterpreterAgent:
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


def test_image_input_classifier_returns_structured_classification() -> None:
    classification = ImageClassification(kind="document", reasoning="It's prose.")
    fake_agent = _FakeImageClassifierAgent(classification)
    classifier = ImageInputClassifier(agent=fake_agent)

    result = classifier.classify(b"fake-bytes", "note.png")

    assert result == classification
    assert len(fake_agent.calls) == 1


async def test_classifier_classify_async_returns_structured_classification() -> None:
    classification = ImageClassification(kind="diagram", reasoning="Boxes and arrows.")
    fake_agent = _FakeImageClassifierAgent(classification)
    classifier = ImageInputClassifier(agent=fake_agent)

    result = await classifier.classify_async(b"fake-bytes", "diagram.png")

    assert result == classification


async def test_classifier_classify_raises_when_called_from_running_loop() -> None:
    # Regression guard for the exact async-route bug Slice 1 caught (see
    # app/analyzer.py's docstring/README "Clean Architecture Migration"):
    # calling the sync bridge from inside a running event loop must raise
    # a clear, actionable error rather than crash confusingly deep inside
    # `asyncio.run()`.
    classification = ImageClassification(kind="document", reasoning="It's prose.")
    fake_agent = _FakeImageClassifierAgent(classification)
    classifier = ImageInputClassifier(agent=fake_agent)

    with pytest.raises(RuntimeError, match="classify_async"):
        classifier.classify(b"fake-bytes", "note.png")


async def test_interpreter_interpret_raises_when_called_from_running_loop() -> None:
    design = SystemDesignArtifact(architecture_summary="A design.")
    fake_agent = _FakeDiagramImageInterpreterAgent(design)
    interpreter = DiagramImageInterpreter(agent=fake_agent)

    with pytest.raises(RuntimeError, match="interpret_async"):
        interpreter.interpret(b"fake-bytes", "diagram.png")


def test_diagram_image_interpreter_returns_structured_design() -> None:
    design = SystemDesignArtifact(architecture_summary="Redrawn architecture.")
    fake_agent = _FakeDiagramImageInterpreterAgent(design)
    interpreter = DiagramImageInterpreter(agent=fake_agent)

    result = interpreter.interpret(b"fake-bytes", "diagram.png")

    assert result.architecture_summary == "Redrawn architecture."
    assert len(fake_agent.calls) == 1


async def test_interpreter_interpret_async_returns_structured_design() -> None:
    design = SystemDesignArtifact(architecture_summary="Redrawn architecture.")
    fake_agent = _FakeDiagramImageInterpreterAgent(design)
    interpreter = DiagramImageInterpreter(agent=fake_agent)

    result = await interpreter.interpret_async(b"fake-bytes", "diagram.png")

    assert result == design


def test_diagram_image_interpreter_passes_previous_design_and_notes_through() -> None:
    previous = SystemDesignArtifact(architecture_summary="Original architecture.")
    refined = SystemDesignArtifact(architecture_summary="Refined architecture.")
    fake_agent = _FakeDiagramImageInterpreterAgent(refined)
    interpreter = DiagramImageInterpreter(agent=fake_agent)

    result = interpreter.interpret(
        b"fake-bytes",
        "diagram.png",
        previous_design=previous,
        notes="Add a queue.",
    )

    assert result.architecture_summary == "Refined architecture."

    [(_, _filename, sent_previous, sent_notes)] = fake_agent.calls
    assert sent_previous == previous
    assert sent_notes == "Add a queue."
