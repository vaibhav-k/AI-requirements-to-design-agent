"""Extract requirements source text from an uploaded document.

File upload is an *additional* way to supply requirements input, alongside
the existing free-text ``user_input`` (see ``app/analyzer.py``'s
``RequirementsAnalyzer.analyze``) — not a replacement for it. Whatever text
comes out of a file here is passed into that same ``analyze()`` call as
``user_input``, so the rest of the requirements pipeline (structuring,
refinement, versioning, persistence) doesn't need to know or care whether
its input was typed or extracted from a document.

Extraction is deliberately routed through a single service — Azure AI
Document Intelligence's ``prebuilt-read`` model — for every non-plain-text
format (PDF, DOCX, PNG, JPEG/JPG), rather than one extraction library per
format (``pypdf`` for PDF, ``python-docx`` for Word, ``pytesseract`` for
images, ...). ``prebuilt-read`` performs OCR and layout-aware text
extraction and, as of the API version this project targets, accepts all of
those formats directly — so a photo of a whiteboard and a born-digital PDF
go through the exact same code path. ``.txt`` is decoded directly instead,
since plain text needs no document analysis at all.

If your Document Intelligence resource is pinned to an older API version
that doesn't yet accept ``.docx`` as an input format, DOCX extraction will
fail with a clear ``DocumentExtractionError`` rather than silently
misbehaving — see the README's "File Upload" section for the workaround
(convert to PDF first) if you hit this.
"""

from __future__ import annotations

import io
import os

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()


class DocumentExtractionError(RuntimeError):
    """Raised when text can't be extracted from an uploaded file."""


# .txt needs no document analysis — it's already the text we want.
_PLAIN_TEXT_EXTENSIONS = frozenset({".txt"})

# Everything else goes through Document Intelligence's prebuilt-read model,
# which handles PDF, DOCX, and image OCR uniformly. See the module
# docstring for why this is one shared path rather than one library per
# format.
_DOCUMENT_INTELLIGENCE_EXTENSIONS = frozenset(
    {".pdf", ".docx", ".png", ".jpg", ".jpeg"}
)

# The subset of the above that could plausibly be a photo/screenshot of a
# system design or workflow diagram rather than prose — PDF/DOCX are
# authored documents and never routed through image classification (see
# ``app/vision.py``'s ``ImageInputClassifier``), only PNG/JPG/JPEG are.
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg"})

SUPPORTED_EXTENSIONS = _PLAIN_TEXT_EXTENSIONS | _DOCUMENT_INTELLIGENCE_EXTENSIONS


def _extension_of(filename: str) -> str:
    _, ext = os.path.splitext(filename)
    return ext.lower()


def is_supported_filename(filename: str) -> bool:
    """Whether ``filename``'s extension can be scanned for requirements."""

    return _extension_of(filename) in SUPPORTED_EXTENSIONS


def is_image_filename(filename: str) -> bool:
    """Whether ``filename`` is one of the image extensions eligible for
    image-input classification (``app/vision.py``) before extraction —
    a PNG/JPG/JPEG might be a document screenshot (routed through the
    existing OCR pipeline below) or a system design/workflow diagram
    (routed straight into architecture generation instead)."""

    return _extension_of(filename) in IMAGE_EXTENSIONS


class RequirementsDocumentExtractor:
    """Extracts plain text from an uploaded requirements source document."""

    def __init__(self) -> None:
        # Built lazily, on first use of a Document-Intelligence-requiring
        # extraction — *not* eagerly at import/construction time the way
        # AZURE_OPENAI_* is required in app/analyzer.py. Uploading a file
        # is optional; a deployment that only ever uses typed text input
        # must keep working without AZURE_DOCUMENT_INTELLIGENCE_* configured
        # at all.
        self._client: DocumentIntelligenceClient | None = None

    def _get_client(self) -> DocumentIntelligenceClient:
        if self._client is not None:
            return self._client

        endpoint = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
        key = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")

        if not endpoint or not key:
            raise DocumentExtractionError(
                "Scanning PDF, Word, or image files for requirements "
                "requires AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and "
                "AZURE_DOCUMENT_INTELLIGENCE_KEY to be configured."
            )

        self._client = DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(key),
        )
        return self._client

    def extract(self, filename: str, content: bytes) -> str:
        """Extract plain text from an uploaded file's raw bytes.

        Dispatches purely on ``filename``'s extension — the caller (the
        upload routes in ``app/api/routes/requirements.py``) is
        responsible for rejecting unsupported extensions before the
        (potentially large) file is even read into memory; this also
        re-checks and raises, rather than assuming the caller always will.
        """

        extension = _extension_of(filename)

        if extension in _PLAIN_TEXT_EXTENSIONS:
            return self._extract_plain_text(content)

        if extension in _DOCUMENT_INTELLIGENCE_EXTENSIONS:
            return self._extract_via_document_intelligence(content)

        raise DocumentExtractionError(
            f"Unsupported file type {extension!r}. Supported types: "
            f"{', '.join(sorted(SUPPORTED_EXTENSIONS))}."
        )

    @staticmethod
    def _extract_plain_text(content: bytes) -> str:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentExtractionError(
                "Could not decode the .txt file as UTF-8 text."
            ) from exc

        if not text.strip():
            raise DocumentExtractionError("The uploaded .txt file is empty.")

        return text

    def _extract_via_document_intelligence(self, content: bytes) -> str:
        client = self._get_client()

        try:
            poller = client.begin_analyze_document(
                "prebuilt-read", body=io.BytesIO(content)
            )
            result = poller.result()
        except DocumentExtractionError:
            raise
        except Exception as exc:
            raise DocumentExtractionError(
                "Azure AI Document Intelligence could not analyze this file."
            ) from exc

        extracted_text: str = result.content

        if not extracted_text.strip():
            raise DocumentExtractionError(
                "No text could be extracted from this file — it may be "
                "blank, corrupted, or an unsupported variant of its format."
            )

        return extracted_text
