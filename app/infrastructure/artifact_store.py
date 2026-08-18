"""Azure Blob Storage-backed requirements/design artifact persistence.

Moved here, verbatim aside from its imports, from ``app/storage.py`` as
part of "Ports + adapters for storage" (see README -> "Clean
Architecture Migration") — ``ArtifactStore`` is the concrete
``app.application.ports.ArtifactStorePort`` implementation, the same
"adapter lives in ``app.infrastructure``" home
``app.infrastructure.session_store.CosmosSessionStore`` already has for
the session-state analogue of this store.
"""

from __future__ import annotations

import logging
import mimetypes
import os

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
)
from dotenv import load_dotenv

from app.application.errors import ArtifactVersionConflict
from app.domain.requirements import StoredArtifact

load_dotenv()

logger = logging.getLogger(__name__)


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


class ArtifactStore:
    """Store requirements and design artifacts in Azure Blob Storage.

    Implements ``app.application.ports.ArtifactStorePort`` structurally —
    no inheritance needed, just matching method signatures.
    """

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

    def save_source_file(
        self,
        session_id: str,
        version: int,
        filename: str,
        content: bytes,
    ) -> str:
        """Persist the original uploaded requirements source document.

        Kept alongside (not instead of) the extracted-text ``StoredArtifact``
        JSON saved by ``save`` — the extracted text feeds the requirements
        pipeline, while this raw file is retained so the original upload
        stays retrievable (e.g. to re-review or re-extract later). The
        blob name preserves the original extension (``suffix``) since it
        varies per upload; ``get_source_file`` therefore lists by prefix
        rather than a fixed name.
        """

        suffix = os.path.splitext(filename)[1].lower()
        blob_name = (
            f"{self.environment}/{session_id}/requirements/v{version}_source{suffix}"
        )

        content_type, _ = mimetypes.guess_type(filename)

        return self._upload(
            blob_name=blob_name,
            content=content,
            content_type=content_type or "application/octet-stream",
            overwrite=True,
        )

    def get_source_file(
        self,
        session_id: str,
        version: int,
    ) -> tuple[bytes, str] | None:
        """The original uploaded file for a requirements version, if any.

        Returns ``(content_bytes, content_type)``, or ``None`` if that
        version wasn't created from an uploaded file (e.g. typed text
        input never has a source file). The extension varies per upload,
        so this lists blobs by the ``v{version}_source`` prefix rather
        than guessing the suffix.
        """

        prefix = f"{self.environment}/{session_id}/requirements/v{version}_source"

        match = None
        for blob in self.container.list_blobs(name_starts_with=prefix):
            match = blob.name
            break

        if match is None:
            return None

        blob_client = self.container.get_blob_client(match)

        try:
            downloader = blob_client.download_blob()
        except ResourceNotFoundError:
            return None

        content_bytes = downloader.readall()
        content_type = (
            downloader.properties.content_settings.content_type
            or "application/octet-stream"
        )

        return content_bytes, content_type

    def _upload(
        self,
        blob_name: str,
        content: str | bytes,
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

        logger.info(
            "Artifact saved to Azure Blob Storage: container=%s blob=%s url=%s",
            self.container.container_name,
            blob_name,
            blob.url,
        )

        return blob_name
