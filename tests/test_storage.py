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
