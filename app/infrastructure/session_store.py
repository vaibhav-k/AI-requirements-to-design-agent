"""Cosmos DB-backed session state for the web API.

The CLI (``app/main.py``) keeps its session state as plain Python objects
(``DesignSession``/``ArchitectureSession``) that live for the lifetime of one
process and one conversation. The web API has no equivalent process to hold
that state in between requests — each request is its own, possibly
different, worker — so a session's requirements/design progress has to be
persisted somewhere a later request can read it back from. One deliberate
choice here: everything else in this project (``ArtifactStore``, the two
analyzers) is written against the *synchronous* Azure/OpenAI SDKs, so this
store uses the synchronous ``azure.cosmos.CosmosClient`` rather than
``azure.cosmos.aio``, and the web routes that use it are defined as plain
``def`` (not ``async def``) so Starlette runs them in a threadpool.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from azure.core import MatchConditions
from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import (
    CosmosAccessConditionFailedError,
    CosmosResourceNotFoundError,
)
from azure.identity import ManagedIdentityCredential
from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings, get_settings
from app.design.models import SystemDesignArtifact
from app.models import RequirementsArtifact

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


class SessionConflictError(RuntimeError):
    """Raised when ``upsert`` loses a race against another writer.

    Surfaces a Cosmos ETag mismatch (HTTP 412) as a store-level error the
    caller can translate into whatever response makes sense for it — an
    HTTP 409 in the web routes — without the routes needing to know
    anything about Cosmos or ETags directly.
    """


class SessionRecord(BaseModel):
    """One requirements-to-design run. Persisted as a Cosmos document (id=session_id).

    Mirrors the CLI's own versioning model: ``requirements_version`` bumps on
    every analyze/refine (``DesignSession.version``); ``design_version`` is
    set once, when architecture is accepted (``ArchitectureSession.version``),
    since this project doesn't support re-generating architecture in place.
    """

    model_config = ConfigDict(populate_by_name=True)

    session_id: str
    owner_oid: str | None = None
    owner_name: str | None = None

    stage: str = "requirements"  # "requirements" | "generating" | "architecture"

    source_text: str = ""
    requirements_version: int = 0
    requirements: RequirementsArtifact | None = None
    requirements_blob: str | None = None

    design_version: int = 0
    design: SystemDesignArtifact | None = None
    design_blob: str | None = None
    diagram_blob: str | None = None

    error: str | None = None

    created_at: str = Field(default_factory=_utcnow_iso)
    updated_at: str = Field(default_factory=_utcnow_iso)

    # Cosmos's own concurrency token (its ``_etag`` system property), carried
    # on the model so a later ``upsert()`` can pass it back as an if-match
    # condition — see ``CosmosSessionStore.upsert``. Populated automatically
    # when a record is read back from Cosmos (``get``/``list_for_owner``);
    # ``None`` on a record that was only ever constructed in Python and never
    # round-tripped, in which case ``upsert`` falls back to an unconditional
    # write. Never sent as part of the document body (``exclude=True``) —
    # Cosmos manages ``_etag`` itself, so this is read-only, not writable.
    etag: str | None = Field(default=None, alias="_etag", exclude=True)

    def to_item(self) -> dict[str, Any]:
        item = self.model_dump(mode="json")
        item["id"] = self.session_id
        return item


@runtime_checkable
class SessionStore(Protocol):
    def create(self, record: SessionRecord) -> SessionRecord: ...

    def get(self, session_id: str) -> SessionRecord | None: ...

    def upsert(self, record: SessionRecord) -> SessionRecord: ...

    def list_for_owner(self, owner_oid: str) -> list[SessionRecord]: ...


class CosmosSessionStore:
    """Synchronous Cosmos-backed session store."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings: Settings = settings or get_settings()
        self._client: Any = None
        self._container: Any = None

    def start(self) -> None:
        """Create the client + ensure database/container exist. Call at startup."""
        s = self._settings
        if s.cosmos_auth_mode == "managed_identity":
            self._client = CosmosClient(
                s.cosmos_endpoint, credential=ManagedIdentityCredential()
            )
        else:
            self._client = CosmosClient(s.cosmos_endpoint, credential=s.cosmos_key)

        database = self._client.create_database_if_not_exists(id=s.cosmos_database)
        self._container = database.create_container_if_not_exists(
            id=s.cosmos_sessions_container,
            partition_key=PartitionKey(path="/session_id"),
        )
        logger.info(
            "Cosmos session store ready: db=%s container=%s",
            s.cosmos_database,
            s.cosmos_sessions_container,
        )

    def close(self) -> None:
        """No-op: the synchronous ``azure.cosmos.CosmosClient`` (unlike its
        ``.aio`` counterpart) exposes no ``close()`` — it issues each request
        over a pooled ``requests.Session`` under the hood rather than holding
        a persistent connection, so there's nothing here to release. Kept as
        a method (rather than removed) so the shutdown call site in
        ``app/web/main.py``'s ``lifespan`` doesn't need to know that.
        """

    def _require_container(self) -> Any:
        if self._container is None:
            raise RuntimeError("CosmosSessionStore.start() was not called.")
        return self._container

    def create(self, record: SessionRecord) -> SessionRecord:
        item = self._require_container().create_item(body=record.to_item())
        record.etag = item.get("_etag")
        return record

    def get(self, session_id: str) -> SessionRecord | None:
        try:
            item = self._require_container().read_item(
                item=session_id, partition_key=session_id
            )
        except CosmosResourceNotFoundError:
            return None
        return SessionRecord.model_validate(item)

    def upsert(self, record: SessionRecord) -> SessionRecord:
        """Persist ``record``, using its ``etag`` as an if-match condition when set.

        ``record.etag`` is populated whenever a record came from ``get()`` (or
        an earlier ``create()``/``upsert()``), so the common case — load,
        mutate, save — is conditional on nothing else having written to this
        session in between. A record with no ``etag`` (never round-tripped
        through Cosmos) writes unconditionally, same as before this existed.

        Raises :class:`SessionConflictError` instead of silently overwriting
        a concurrent writer's change when the condition fails (Cosmos 412).
        """
        record.updated_at = _utcnow_iso()
        kwargs: dict[str, Any] = {}
        if record.etag is not None:
            kwargs["etag"] = record.etag
            kwargs["match_condition"] = MatchConditions.IfNotModified

        try:
            item = self._require_container().upsert_item(
                body=record.to_item(), **kwargs
            )
        except CosmosAccessConditionFailedError as exc:
            raise SessionConflictError(
                f"Session {record.session_id!r} was modified by another "
                "request in between; retry."
            ) from exc

        record.etag = item.get("_etag")
        return record

    def list_for_owner(self, owner_oid: str) -> list[SessionRecord]:
        """Every session started by one user, newest first.

        Cross-partition (the container is partitioned by ``session_id``, and
        one user's sessions are spread across all of them) — filtered
        server-side on ``owner_oid`` rather than reading everything and
        filtering here. Returns ``[]`` for a falsy ``owner_oid`` rather than
        querying, since an unowned or anonymous caller has no sessions to
        find by definition (see ``app/api/ownership.py``'s "unowned records
        are nobody's" rule).
        """
        if not owner_oid:
            return []
        query = "SELECT * FROM c WHERE c.owner_oid = @owner ORDER BY c._ts DESC"
        return [
            SessionRecord.model_validate(item)
            for item in self._require_container().query_items(
                query=query,
                parameters=[{"name": "@owner", "value": owner_oid}],
                enable_cross_partition_query=True,
            )
        ]
