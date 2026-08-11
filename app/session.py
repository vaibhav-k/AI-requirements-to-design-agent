from __future__ import annotations

import uuid
from datetime import UTC, datetime

from .analyzer import RequirementsAnalyzer
from .models import (
    RequirementsArtifact,
    StoredArtifact,
)
from .storage import ArtifactStore


class DesignSession:
    """Manage requirements analysis and artifact versioning."""

    def __init__(
        self,
        analyzer: RequirementsAnalyzer,
        store: ArtifactStore,
    ) -> None:
        self.session_id = str(uuid.uuid4())

        self.analyzer = analyzer
        self.store = store

        self.version = 0
        self.current_artifact: RequirementsArtifact | None = None

    def analyze(
        self,
        user_input: str,
    ) -> StoredArtifact:
        """Analyze input, increment version, and persist the result."""

        self.version += 1

        artifact = self.analyzer.analyze(
            user_input=user_input,
            previous_artifact=self.current_artifact,
        )

        self.current_artifact = artifact

        stored_artifact = StoredArtifact(
            artifact_id=str(uuid.uuid4()),
            session_id=self.session_id,
            artifact_type="requirements",
            version=self.version,
            created_at=datetime.now(UTC).isoformat(),
            source_text=user_input,
            requirements=artifact,
        )

        blob_name = self.store.save(stored_artifact)

        print(
            "\nSaved artifact:"
            f"\n  Session: {self.session_id}"
            f"\n  Version: {self.version}"
            f"\n  Blob: {blob_name}"
        )

        return stored_artifact
