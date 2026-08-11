from __future__ import annotations

import os

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
)
from dotenv import load_dotenv

from app.models import StoredArtifact

load_dotenv()


AZURE_CONNECTION_STRING = os.getenv(
    "AZURE_STORAGE_CONNECTION_STRING",
    "",
)

AZURE_CONTAINER = os.getenv(
    "AZURE_STORAGE_CONTAINER",
    "requirements",
)

AZURE_STORAGE_ENVIRONMENT = os.getenv(
    "AZURE_STORAGE_ENVIRONMENT",
    "dev",
)


class ArtifactVersionConflict(RuntimeError):
    """Raised when an artifact version already exists."""


class ArtifactStore:
    """Store requirements and design artifacts in Azure Blob Storage."""

    def __init__(
        self,
        connection_string: str,
        container_name: str,
        environment: str = AZURE_STORAGE_ENVIRONMENT,
    ) -> None:
        if not connection_string:
            raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is required.")

        self.service = BlobServiceClient.from_connection_string(connection_string)

        self.container = self.service.get_container_client(container_name)

        self.environment = environment

        self._ensure_container()

    def _ensure_container(self) -> None:
        try:
            self.container.create_container()
        except ResourceExistsError:
            pass

    def save(
        self,
        artifact: StoredArtifact,
    ) -> str:
        """Save a requirements artifact."""

        blob_name = (
            f"{self.environment}/"
            f"{artifact.session_id}/"
            f"requirements/"
            f"v{artifact.version}.json"
        )

        content = artifact.model_dump_json(indent=2)

        return self._upload(
            blob_name=blob_name,
            content=content,
            content_type="application/json",
            overwrite=True,
        )

    def get_latest_design_version(self, session_id: str) -> int:
        """Return the latest persisted design JSON version for a session."""

        prefix = f"{self.environment}/{session_id}/design/"

        versions: list[int] = []

        for blob in self.container.list_blobs(name_starts_with=prefix):
            name = blob.name

            if not name.startswith(prefix):
                continue

            if not name.endswith(".json"):
                continue

            filename = name.rsplit("/", 1)[-1]

            if not filename.startswith("v"):
                continue

            version_text = filename[1:-5]  # Remove "v" and ".json"

            try:
                versions.append(int(version_text))
            except ValueError:
                continue

        return max(versions, default=0)

    def save_design_json(
        self,
        session_id: str,
        version: int,
        content: str,
    ) -> str:
        """Create a design JSON version without overwriting it."""

        blob_name = f"{self.environment}/{session_id}/design/v{version}.json"

        try:
            return self._upload(
                blob_name=blob_name,
                content=content,
                content_type="application/json",
                overwrite=False,
            )
        except ResourceExistsError as exc:
            raise ArtifactVersionConflict(
                f"Design version {version} already exists."
            ) from exc

    def save_design_svg(
        self,
        session_id: str,
        version: int,
        content: str,
    ) -> str:
        """Create the SVG for an existing design version."""

        blob_name = f"{self.environment}/{session_id}/design/v{version}.svg"

        return self._upload(
            blob_name=blob_name,
            content=content,
            content_type="image/svg+xml",
            overwrite=False,
        )

    def delete_design_json(
        self,
        session_id: str,
        version: int,
    ) -> None:
        """Delete a design JSON artifact if it exists."""

        blob_name = f"{self.environment}/{session_id}/design/v{version}.json"

        self.container.delete_blob(
            blob_name,
            delete_snapshots="include",
        )

    def delete_design_svg(
        self,
        session_id: str,
        version: int,
    ) -> None:
        """Delete a design SVG artifact if it exists."""

        blob_name = f"{self.environment}/{session_id}/design/v{version}.svg"

        self.container.delete_blob(
            blob_name,
            delete_snapshots="include",
        )

    def _upload(
        self,
        blob_name: str,
        content: str,
        content_type: str,
        overwrite: bool,
    ) -> str:
        blob = self.container.get_blob_client(blob_name)

        blob.upload_blob(
            content,
            overwrite=overwrite,
            content_settings=ContentSettings(
                content_type=content_type,
            ),
        )

        return blob_name
