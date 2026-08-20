from __future__ import annotations

from app.application.use_cases.classify_image import ClassifyImageUseCase
from app.domain.vision import ImageClassification


class _FakePort:
    def __init__(self, classification: ImageClassification) -> None:
        self.classification = classification
        self.calls: list[tuple[bytes, str]] = []

    async def classify(self, content: bytes, filename: str) -> ImageClassification:
        self.calls.append((content, filename))
        return self.classification


async def test_execute_delegates_to_the_port() -> None:
    classification = ImageClassification(kind="document", reasoning="It's prose.")
    port = _FakePort(classification)
    use_case = ClassifyImageUseCase(agent=port)

    result = await use_case.execute(b"bytes", "note.png")

    assert result == classification
    assert port.calls == [(b"bytes", "note.png")]
