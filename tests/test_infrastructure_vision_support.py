from __future__ import annotations

from agent_framework import Content

from app.infrastructure.agents.vision_support import image_content


def test_image_content_maps_png_extension_to_media_type() -> None:
    content = image_content(b"fake-bytes", "diagram.png")

    assert isinstance(content, Content)
    assert content.media_type == "image/png"


def test_image_content_maps_jpg_extension_to_jpeg_media_type() -> None:
    # ".jpg" -> "image/jpeg", not the literal (invalid) "image/jpg" —
    # matches the previous `app.vision._data_url`'s extension handling.
    content = image_content(b"fake-bytes", "photo.jpg")

    assert content.media_type == "image/jpeg"


def test_image_content_defaults_to_png_when_no_extension() -> None:
    content = image_content(b"fake-bytes", "upload")

    assert content.media_type == "image/png"
