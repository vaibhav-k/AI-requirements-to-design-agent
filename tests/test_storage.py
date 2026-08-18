from __future__ import annotations

from unittest.mock import MagicMock, patch

from azure.storage.blob import BlobServiceClient

from app.models import (
    RequirementsArtifact,
    StoredArtifact,
)
from app.storage import ArtifactStore


def create_stored_artifact() -> StoredArtifact:
    """Create a representative stored artifact."""

    requirements = RequirementsArtifact(
        summary="Test requirements.",
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

    return StoredArtifact(
        artifact_id="artifact-123",
        session_id="session-123",
        artifact_type="requirements",
        version=1,
        created_at="2026-08-11T10:00:00+00:00",
        source_text="Build a requirements analyzer.",
        requirements=requirements,
    )


@patch("app.storage.BlobServiceClient")
def test_save_uploads_json(
    mock_blob_service: MagicMock,
) -> None:
    """Saving an artifact should upload JSON to the expected blob."""

    service = mock_blob_service.from_connection_string.return_value
    container = service.get_container_client.return_value
    blob = container.get_blob_client.return_value

    store = ArtifactStore(
        "test-connection",
        "requirements",
        environment="dev",
    )

    artifact = create_stored_artifact()

    blob_name = store.save(artifact)

    assert blob_name == ("dev/session-123/requirements/v1.json")

    container.get_blob_client.assert_called_once_with(
        "dev/session-123/requirements/v1.json"
    )

    blob.upload_blob.assert_called_once()


@patch("app.storage.BlobServiceClient")
def test_close_closes_the_underlying_blob_service_client(
    mock_blob_service: MagicMock,
) -> None:
    """close() must call a method that actually exists on BlobServiceClient.

    Uses ``spec=BlobServiceClient`` (via autospec on the class) so that if
    ``close()`` ever called something the real SDK doesn't expose, the test
    would fail the same way the real client would — see the equivalent
    regression test in test_session_store.py for why that distinction
    matters (a plain MagicMock would accept any call silently).
    """
    mock_blob_service.from_connection_string.return_value = MagicMock(
        spec=BlobServiceClient
    )

    store = ArtifactStore("test-connection", "requirements", environment="dev")
    store.close()

    store.service.close.assert_called_once()  # type: ignore[attr-defined]


@patch("app.storage.BlobServiceClient")
def test_save_source_file_uploads_the_raw_bytes_with_the_original_extension(
    mock_blob_service: MagicMock,
) -> None:
    service = mock_blob_service.from_connection_string.return_value
    container = service.get_container_client.return_value
    blob = container.get_blob_client.return_value

    store = ArtifactStore("test-connection", "requirements", environment="dev")

    blob_name = store.save_source_file("session-123", 1, "spec.pdf", b"pdf bytes")

    assert blob_name == "dev/session-123/requirements/v1_source.pdf"
    container.get_blob_client.assert_called_once_with(
        "dev/session-123/requirements/v1_source.pdf"
    )
    blob.upload_blob.assert_called_once()
    args, kwargs = blob.upload_blob.call_args
    assert args[0] == b"pdf bytes"
    assert kwargs["content_settings"].content_type == "application/pdf"


@patch("app.storage.BlobServiceClient")
def test_get_source_file_returns_none_when_nothing_was_uploaded(
    mock_blob_service: MagicMock,
) -> None:
    service = mock_blob_service.from_connection_string.return_value
    container = service.get_container_client.return_value
    container.list_blobs.return_value = []

    store = ArtifactStore("test-connection", "requirements", environment="dev")

    assert store.get_source_file("session-123", 1) is None


@patch("app.storage.BlobServiceClient")
def test_get_source_file_downloads_the_matching_blob_by_prefix(
    mock_blob_service: MagicMock,
) -> None:
    service = mock_blob_service.from_connection_string.return_value
    container = service.get_container_client.return_value

    matching_blob = MagicMock()
    matching_blob.name = "dev/session-123/requirements/v1_source.pdf"
    container.list_blobs.return_value = [matching_blob]

    blob_client = container.get_blob_client.return_value
    downloader = blob_client.download_blob.return_value
    downloader.readall.return_value = b"pdf bytes"
    downloader.properties.content_settings.content_type = "application/pdf"

    store = ArtifactStore("test-connection", "requirements", environment="dev")

    result = store.get_source_file("session-123", 1)

    assert result == (b"pdf bytes", "application/pdf")
    container.list_blobs.assert_called_once_with(
        name_starts_with="dev/session-123/requirements/v1_source"
    )
    container.get_blob_client.assert_called_with(
        "dev/session-123/requirements/v1_source.pdf"
    )
