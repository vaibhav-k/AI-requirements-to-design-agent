from __future__ import annotations

import os

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
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

    def close(self) -> None:
        """Release the underlying HTTP session. Call once, at shutdown.

        The CLI (``app/main.py``) never calls this — a short-lived process
        exiting cleans up its own sockets — but the web API's ``lifespan``
        does, since a long-running server should release what it opened.
        """
        self.service.close()

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

    def _list_versions(self, prefix: str, suffix: str) -> list[int]:
        """Every version number persisted under ``prefix`` ending in ``suffix``.

        Blob names are the source of truth for what versions exist — nothing
        else (no separate index/manifest) tracks it — since each version is
        its own immutable blob (``v{n}{suffix}``, never overwritten once
        written; see ``save_design_json``/``save_design_svg``'s
        ``overwrite=False``). Sorted ascending so callers get a stable,
        oldest-first version history without re-sorting themselves.
        """
        versions: list[int] = []

        for blob in self.container.list_blobs(name_starts_with=prefix):
            name = blob.name

            if not name.startswith(prefix) or not name.endswith(suffix):
                continue

            filename = name.rsplit("/", 1)[-1]

            if not filename.startswith("v"):
                continue

            version_text = filename[1 : -len(suffix)]  # strip "v" prefix and suffix

            try:
                versions.append(int(version_text))
            except ValueError:
                continue

        return sorted(versions)

    def _download(self, blob_name: str) -> str | None:
        """The text content of ``blob_name``, or ``None`` if it doesn't exist."""
        try:
            downloader = self.container.get_blob_client(blob_name).download_blob()
        except ResourceNotFoundError:
            return None
        return downloader.readall().decode("utf-8")

    def get_latest_design_version(self, session_id: str) -> int:
        """Return the latest persisted design JSON version for a session."""

        versions = self.list_design_versions(session_id)
        return max(versions, default=0)

    def list_requirements_versions(self, session_id: str) -> list[int]:
        """Every requirements version persisted for this session, oldest first."""

        prefix = f"{self.environment}/{session_id}/requirements/"
        return self._list_versions(prefix, ".json")

    def get_requirements_json(self, session_id: str, version: int) -> str | None:
        """The raw ``StoredArtifact`` JSON for one requirements version.

        ``None`` if that version was never persisted (or was for a
        different session) — the caller decides what that means (404,
        typically).
        """
        blob_name = f"{self.environment}/{session_id}/requirements/v{version}.json"
        return self._download(blob_name)

    def list_design_versions(self, session_id: str) -> list[int]:
        """Every design version persisted for this session, oldest first."""

        prefix = f"{self.environment}/{session_id}/design/"
        return self._list_versions(prefix, ".json")

    def get_design_json(self, session_id: str, version: int) -> str | None:
        """The raw ``SystemDesignArtifact`` JSON for one design version.

        Unlike requirements' ``StoredArtifact`` envelope, this blob *is*
        the design JSON directly — see ``ArchitectureSession.generate``.
        """
        blob_name = f"{self.environment}/{session_id}/design/v{version}.json"
        return self._download(blob_name)

    def get_design_svg(self, session_id: str, version: int) -> str | None:
        """The raw architecture diagram SVG markup for one design version."""

        blob_name = f"{self.environment}/{session_id}/design/v{version}.svg"
        return self._download(blob_name)

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
