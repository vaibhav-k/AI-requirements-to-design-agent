"""Image input classification for uploaded PNG/JPG/JPEG files.

An uploaded image can mean two very different things to this pipeline:

* A screenshot or photo of TEXT — requirements notes, a spec, an email, a
  whiteboard of bullet points — meant to be *read*. These already go
  through OCR (``app/ingestion.py``'s Document Intelligence extraction)
  and into the normal requirements-analysis pipeline.
* A photo or screenshot of a SYSTEM DESIGN / WORKFLOW DIAGRAM — boxes and
  arrows depicting components, services, or data flow — meant to be
  *understood structurally*, not read as prose. Running OCR + requirements
  analysis on this would, at best, transcribe box labels as if they were
  requirements text, and at worst produce nonsense.

``ImageInputClassifier`` decides which of the two an uploaded image is.
``DiagramImageInterpreter`` handles the second case: it derives a
structured ``SystemDesignArtifact`` directly from the image — "redraw this
as a clean, well-architected system design" — reusing the exact schema
``SystemDesignAnalyzer`` (``app/design/analyzer.py``) produces from text,
so everything downstream (validation, diagram rendering, versioning,
refinement, approval) treats an image-derived design exactly like a
text-derived one. See ``app/api/routes/requirements.py``'s upload routes
for how the two are wired together.

Both classes use the Responses API's multimodal input (an ``input_image``
content part alongside ``input_text``), which requires a vision-capable
Azure OpenAI deployment — the same ``AZURE_OPENAI_MODEL`` every other
analyzer in this project already requires, so no new environment variable
is introduced here.
"""

from __future__ import annotations

import base64
import os
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.responses import ResponseInputItemParam
from pydantic import BaseModel, Field

from app.design.models import SystemDesignArtifact

load_dotenv()


def _required_environment_variable(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"{name} environment variable is required.")

    return value


AZURE_OPENAI_API_KEY = _required_environment_variable("AZURE_OPENAI_API_KEY")

AZURE_OPENAI_ENDPOINT = _required_environment_variable("AZURE_OPENAI_ENDPOINT")

AZURE_OPENAI_MODEL = _required_environment_variable("AZURE_OPENAI_MODEL")


_EXTENSION_TO_MIME = {"jpg": "jpeg"}


def _data_url(content: bytes, filename: str) -> str:
    """A ``data:`` URL for an uploaded image's raw bytes — the Responses
    API's ``input_image`` content part accepts either a hosted URL or an
    inline data URL; inline avoids needing anywhere to host the file first,
    matching how everything else in this project keeps an upload's bytes
    in memory for the duration of one request."""

    extension = os.path.splitext(filename)[1].lower().lstrip(".") or "png"
    mime = _EXTENSION_TO_MIME.get(extension, extension)
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:image/{mime};base64,{encoded}"


class ImageClassification(BaseModel):
    """Result of classifying an uploaded image — see the module docstring."""

    kind: Literal["document", "diagram"]
    reasoning: str = Field(
        description="One sentence explaining why this image was classified this way."
    )


class ImageClassificationError(RuntimeError):
    """Raised when an uploaded image can't be classified."""


class DiagramInterpretationError(RuntimeError):
    """Raised when a diagram image can't be interpreted into an architecture."""


class ImageInputClassifier:
    """Classifies an uploaded image as a document screenshot or a system
    design/workflow diagram."""

    def __init__(self, model: str = AZURE_OPENAI_MODEL) -> None:
        self.client = OpenAI(
            api_key=AZURE_OPENAI_API_KEY,
            base_url=AZURE_OPENAI_ENDPOINT.rstrip("/") + "/",
        )
        self.model = model

    def classify(self, content: bytes, filename: str) -> ImageClassification:
        """Classify ``content`` (an uploaded image's raw bytes) as a
        ``"document"`` screenshot or a ``"diagram"``."""

        # Explicitly typed as `list[ResponseInputItemParam]` — the exact
        # element type `responses.parse`'s `input` parameter expects
        # (rather than left for Pyright to infer from the literal, or
        # annotated as `list[EasyInputMessageParam]`, one member of that
        # union: `list` is invariant, so a `list[EasyInputMessageParam]`
        # doesn't type-check as a `list[ResponseInputItemParam]` even
        # though every `EasyInputMessageParam` *is* one). This also
        # makes the user message's `content` — a list of
        # input_text/input_image parts, not a plain string like the
        # system message's — type-check against
        # `EasyInputMessageParam.content`'s
        # `str | list[ResponseInputTextParam | ResponseInputImageParam |
        # ResponseInputFileParam]` union instead of widening to a bare
        # `dict[str, ...]` that matches none of `responses.parse`'s
        # accepted input item types.
        messages: list[ResponseInputItemParam] = [
            {
                "role": "system",
                "content": (
                    "You classify an uploaded image for a "
                    "requirements-to-design tool. Decide whether it is:\n\n"
                    "(a) 'document' — a screenshot or photo of TEXT meant "
                    "to be read: requirements notes, an email, a spec, a "
                    "whiteboard of bullet points, a form, a table, a "
                    "written note. Even if it contains a few small boxes "
                    "or icons, classify it as 'document' if its primary "
                    "content is prose or lists of text.\n\n"
                    "(b) 'diagram' — a SYSTEM DESIGN or WORKFLOW DIAGRAM: "
                    "boxes/nodes connected by arrows depicting components, "
                    "services, data flow, a sequence, or an architecture, "
                    "meant to be understood as a structural drawing rather "
                    "than read as prose."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Classify this image."},
                    {
                        "type": "input_image",
                        "image_url": _data_url(content, filename),
                        "detail": "auto",
                    },
                ],
            },
        ]

        try:
            response = self.client.responses.parse(
                model=self.model,
                input=messages,
                text_format=ImageClassification,
            )
        except Exception as exc:
            raise ImageClassificationError(
                "Azure OpenAI could not classify the uploaded image."
            ) from exc

        if response.output_parsed is None:
            raise ImageClassificationError(
                "Azure OpenAI returned no image classification."
            )

        return response.output_parsed


class DiagramImageInterpreter:
    """Derives a structured system design directly from a diagram image."""

    def __init__(self, model: str = AZURE_OPENAI_MODEL) -> None:
        self.client = OpenAI(
            api_key=AZURE_OPENAI_API_KEY,
            base_url=AZURE_OPENAI_ENDPOINT.rstrip("/") + "/",
        )
        self.model = model

    def interpret(
        self,
        content: bytes,
        filename: str,
        previous_design: SystemDesignArtifact | None = None,
        notes: str | None = None,
    ) -> SystemDesignArtifact:
        """Interpret ``content`` (an uploaded diagram image's raw bytes)
        into a redrawn, well-architected ``SystemDesignArtifact``.

        Passing ``previous_design`` treats the image as refining that
        design rather than replacing it wholesale, the same "preserve what
        still applies" contract ``SystemDesignAnalyzer.analyze`` follows
        for text-based refinement.
        """

        prompt_text = self._build_prompt(previous_design, notes)

        # See `ImageInputClassifier.classify`'s `messages` comment for why
        # this needs an explicit `list[ResponseInputItemParam]`
        # annotation rather than being inlined into the
        # `responses.parse(input=...)` call directly.
        messages: list[ResponseInputItemParam] = [
            {
                "role": "system",
                "content": (
                    "You are a senior software architect. Look at the "
                    "supplied system design / workflow diagram image and "
                    "redraw it as a clean, well-architected system design: "
                    "identify every component, interface, and external "
                    "dependency it depicts, correct anything that is "
                    "structurally unclear, redundant, or inconsistent, and "
                    "return the requested structured architecture — not a "
                    "description of the image."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt_text},
                    {
                        "type": "input_image",
                        "image_url": _data_url(content, filename),
                        "detail": "auto",
                    },
                ],
            },
        ]

        try:
            response = self.client.responses.parse(
                model=self.model,
                input=messages,
                text_format=SystemDesignArtifact,
            )
        except Exception as exc:
            raise DiagramInterpretationError(
                "Azure OpenAI could not interpret the uploaded diagram."
            ) from exc

        if response.output_parsed is None:
            raise DiagramInterpretationError(
                "Azure OpenAI returned no parsed system design from the diagram."
            )

        return response.output_parsed

    @staticmethod
    def _build_prompt(
        previous_design: SystemDesignArtifact | None,
        notes: str | None,
    ) -> str:
        refinement_context = ""

        if previous_design is not None:
            refinement_context = f"""
This image refines a previously generated architecture rather than
replacing it outright.

Previous architecture:

{previous_design.model_dump_json(indent=2)}

Preserve components, interfaces, and external dependencies that are still
consistent with the image; apply whatever the image adds or changes. Do
not silently remove or rename existing components, interfaces, or
dependencies unless the image clearly calls for it. Preserve each
existing component's "domain" string exactly as-is unless the image
clearly moves it to a different group; give any newly added component a
domain consistent with the existing set.
"""

        notes_context = (
            f"\nAdditional notes from the uploader:\n{notes}\n" if notes else ""
        )

        return f"""
Examine the attached image of a system design or workflow diagram.
{refinement_context}{notes_context}
Identify:

- Every major logical component depicted (boxes/nodes), each with a
  unique ID, a name, and its responsibility.
- Each component's "domain" — a short group/category name. If the image
  itself visually groups components (a labeled outer box/section/swimlane
  containing several inner boxes, a color-coded region, etc.), use that
  section's label as the domain, character-for-character, for every
  component inside it. If the image has no visible grouping, infer a
  small number of sensible domains (roughly 3-8) from what the
  components do, and use the SAME domain string for every component that
  belongs together — this is what lets the redrawn diagram visually
  cluster related components instead of scattering them.
- Every interface/relationship between components (arrows), each with a
  unique ID, name, purpose, source component, and target component.
- Every external dependency depicted (third-party services, databases, or
  external systems drawn distinctly from the system's own components),
  each with a unique ID, name, purpose, and which components use it.
- Open questions or assumptions needed to fill gaps the image leaves
  ambiguous — an unlabeled arrow, an illegible or ambiguous box.

Return the redrawn architecture as the requested structured format: a
clean, well-architected version of what the image depicts, not a literal
transcription of any illegible or inconsistent labeling in the source
image.
"""
