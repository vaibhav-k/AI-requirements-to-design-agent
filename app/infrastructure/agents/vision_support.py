"""Shared helper for the Microsoft Agent Framework vision adapters.

Both ``image_classifier_agent.py`` and
``diagram_image_interpreter_agent.py`` need to turn an uploaded image's
raw bytes into the multimodal ``Content`` part ``Agent.run`` accepts
alongside a text prompt (via ``agent_framework.Message(role="user",
contents=[...])`` — see either adapter for the full call site). Split
out so that conversion — including the filename-extension-to-MIME-type
mapping — has exactly one implementation instead of two copies drifting
apart.
"""

from __future__ import annotations

import os

from agent_framework import Content

# Mirrors the previous ``app.vision._data_url``'s extension handling: a
# ``.jpg`` upload's MIME subtype is ``jpeg``, not the literal extension.
_EXTENSION_TO_MIME_SUBTYPE = {"jpg": "jpeg"}


def image_content(content: bytes, filename: str) -> Content:
    """A Microsoft Agent Framework ``Content`` part for an uploaded
    image's raw bytes, media-typed from ``filename``'s extension.
    Defaults to ``image/png`` when ``filename`` has no extension, the
    same fallback ``app.vision._data_url`` used."""

    extension = os.path.splitext(filename)[1].lower().lstrip(".") or "png"
    subtype = _EXTENSION_TO_MIME_SUBTYPE.get(extension, extension)
    return Content.from_data(content, media_type=f"image/{subtype}")
