from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.ingestion import (
    SUPPORTED_EXTENSIONS,
    DocumentExtractionError,
    RequirementsDocumentExtractor,
    is_supported_filename,
)


def test_supported_extensions_cover_every_format_the_user_asked_for() -> None:
    assert SUPPORTED_EXTENSIONS == {
        ".txt",
        ".pdf",
        ".docx",
        ".png",
        ".jpg",
        ".jpeg",
    }


@pytest.mark.parametrize(
    "filename",
    ["spec.txt", "spec.PDF", "spec.docx", "photo.PNG", "photo.jpg", "photo.jpeg"],
)
def test_is_supported_filename_accepts_every_supported_extension(
    filename: str,
) -> None:
    assert is_supported_filename(filename) is True


@pytest.mark.parametrize("filename", ["spec.doc", "spec.exe", "spec", "spec.zip"])
def test_is_supported_filename_rejects_unsupported_extensions(filename: str) -> None:
    assert is_supported_filename(filename) is False


def test_extract_decodes_plain_text_directly() -> None:
    extractor = RequirementsDocumentExtractor()

    text = extractor.extract("spec.txt", b"Build a todo app.")

    assert text == "Build a todo app."


def test_extract_rejects_empty_plain_text() -> None:
    extractor = RequirementsDocumentExtractor()

    with pytest.raises(DocumentExtractionError, match="empty"):
        extractor.extract("spec.txt", b"   ")


def test_extract_rejects_non_utf8_plain_text() -> None:
    extractor = RequirementsDocumentExtractor()

    with pytest.raises(DocumentExtractionError, match="UTF-8"):
        extractor.extract("spec.txt", b"\xff\xfe\x00")


def test_extract_rejects_unsupported_extension() -> None:
    extractor = RequirementsDocumentExtractor()

    with pytest.raises(DocumentExtractionError, match="Unsupported file type"):
        extractor.extract("spec.exe", b"binary")


def test_extract_raises_when_document_intelligence_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", raising=False)
    extractor = RequirementsDocumentExtractor()

    with pytest.raises(DocumentExtractionError, match="AZURE_DOCUMENT_INTELLIGENCE"):
        extractor.extract("spec.pdf", b"%PDF-1.4")


def test_extract_via_document_intelligence_returns_the_analyzed_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://example.test")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "fake-key")

    extractor = RequirementsDocumentExtractor()

    fake_client = MagicMock()
    fake_result = MagicMock()
    fake_result.content = "Extracted requirements text."
    fake_client.begin_analyze_document.return_value.result.return_value = fake_result

    with patch("app.ingestion.DocumentIntelligenceClient", return_value=fake_client):
        text = extractor.extract("spec.pdf", b"%PDF-1.4 fake bytes")

    assert text == "Extracted requirements text."
    fake_client.begin_analyze_document.assert_called_once()
    args, kwargs = fake_client.begin_analyze_document.call_args
    assert args[0] == "prebuilt-read"
    assert kwargs["body"].getvalue() == b"%PDF-1.4 fake bytes"


def test_extract_via_document_intelligence_reuses_the_client_across_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://example.test")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "fake-key")

    extractor = RequirementsDocumentExtractor()
    fake_result = MagicMock()
    fake_result.content = "Text."

    with patch("app.ingestion.DocumentIntelligenceClient") as mock_client_cls:
        poller = mock_client_cls.return_value.begin_analyze_document.return_value
        poller.result.return_value = fake_result

        extractor.extract("a.pdf", b"bytes-a")
        extractor.extract("b.png", b"bytes-b")

    mock_client_cls.assert_called_once()


def test_extract_via_document_intelligence_raises_when_no_text_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://example.test")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "fake-key")

    extractor = RequirementsDocumentExtractor()
    fake_result = MagicMock()
    fake_result.content = "   "
    fake_client = MagicMock()
    fake_client.begin_analyze_document.return_value.result.return_value = fake_result

    with patch("app.ingestion.DocumentIntelligenceClient", return_value=fake_client):
        with pytest.raises(DocumentExtractionError, match="No text could be extracted"):
            extractor.extract("photo.png", b"fake image bytes")


def test_extract_via_document_intelligence_wraps_sdk_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://example.test")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "fake-key")

    extractor = RequirementsDocumentExtractor()
    fake_client = MagicMock()
    fake_client.begin_analyze_document.side_effect = RuntimeError("boom")

    with patch("app.ingestion.DocumentIntelligenceClient", return_value=fake_client):
        with pytest.raises(DocumentExtractionError, match="could not analyze"):
            extractor.extract("spec.docx", b"docx bytes")
