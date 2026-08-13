from __future__ import annotations

from unittest.mock import MagicMock, patch

from azure.core import MatchConditions
from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import (
    CosmosAccessConditionFailedError,
    CosmosResourceNotFoundError,
)

from app.config import Settings
from app.infrastructure.session_store import (
    CosmosSessionStore,
    SessionConflictError,
    SessionRecord,
)


def make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "cosmos_endpoint": "https://example.documents.azure.com:443/",
        "cosmos_key": "test-key",
        "cosmos_database": "test-db",
        "cosmos_sessions_container": "test-sessions",
        "cosmos_auth_mode": "key",
    }
    defaults.update(overrides)
    return Settings.model_validate(defaults)


@patch("app.infrastructure.session_store.CosmosClient")
def test_start_creates_database_and_container_with_key_auth(
    mock_cosmos_client: MagicMock,
) -> None:
    settings = make_settings()
    store = CosmosSessionStore(settings)

    store.start()

    mock_cosmos_client.assert_called_once_with(
        settings.cosmos_endpoint, credential=settings.cosmos_key
    )
    database = mock_cosmos_client.return_value.create_database_if_not_exists
    database.assert_called_once_with(id="test-db")
    database.return_value.create_container_if_not_exists.assert_called_once()


@patch("app.infrastructure.session_store.ManagedIdentityCredential")
@patch("app.infrastructure.session_store.CosmosClient")
def test_start_uses_managed_identity_when_configured(
    mock_cosmos_client: MagicMock,
    mock_credential: MagicMock,
) -> None:
    settings = make_settings(cosmos_auth_mode="managed_identity")
    store = CosmosSessionStore(settings)

    store.start()

    mock_cosmos_client.assert_called_once_with(
        settings.cosmos_endpoint, credential=mock_credential.return_value
    )


def test_get_raises_before_start_is_called() -> None:
    store = CosmosSessionStore(make_settings())

    try:
        store.get("some-session")
    except RuntimeError as exc:
        assert "start()" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError before start() is called.")


@patch("app.infrastructure.session_store.CosmosClient")
def test_create_persists_the_record_as_an_item(mock_cosmos_client: MagicMock) -> None:
    store = CosmosSessionStore(make_settings())
    store.start()
    container = store._container
    container.create_item.return_value = {"id": "abc-123", "_etag": '"etag-1"'}

    record = SessionRecord(session_id="abc-123")
    result = store.create(record)

    assert result is record
    container.create_item.assert_called_once()
    body = container.create_item.call_args.kwargs["body"]
    assert body["id"] == "abc-123"
    assert body["session_id"] == "abc-123"
    assert "etag" not in body and "_etag" not in body


@patch("app.infrastructure.session_store.CosmosClient")
def test_create_captures_the_etag_cosmos_returns(
    mock_cosmos_client: MagicMock,
) -> None:
    """The created item's ``_etag`` must be captured onto the record so an
    immediately-following ``upsert()`` (e.g. in the same request) is
    conditional rather than unconditional."""
    store = CosmosSessionStore(make_settings())
    store.start()
    store._container.create_item.return_value = {"id": "abc-123", "_etag": '"etag-1"'}

    record = store.create(SessionRecord(session_id="abc-123"))

    assert record.etag == '"etag-1"'


@patch("app.infrastructure.session_store.CosmosClient")
def test_get_returns_none_when_not_found(mock_cosmos_client: MagicMock) -> None:
    store = CosmosSessionStore(make_settings())
    store.start()
    store._container.read_item.side_effect = (
        CosmosResourceNotFoundError()  # type: ignore[no-untyped-call]
    )

    assert store.get("missing") is None


@patch("app.infrastructure.session_store.CosmosClient")
def test_get_returns_a_validated_record_when_found(
    mock_cosmos_client: MagicMock,
) -> None:
    store = CosmosSessionStore(make_settings())
    store.start()
    store._container.read_item.return_value = {
        "id": "abc-123",
        "session_id": "abc-123",
        "stage": "requirements",
    }

    record = store.get("abc-123")

    assert record is not None
    assert record.session_id == "abc-123"
    assert record.stage == "requirements"


@patch("app.infrastructure.session_store.CosmosClient")
def test_get_populates_etag_from_the_stored_items_system_property(
    mock_cosmos_client: MagicMock,
) -> None:
    store = CosmosSessionStore(make_settings())
    store.start()
    store._container.read_item.return_value = {
        "id": "abc-123",
        "session_id": "abc-123",
        "_etag": '"etag-1"',
    }

    record = store.get("abc-123")

    assert record is not None
    assert record.etag == '"etag-1"'


@patch("app.infrastructure.session_store.CosmosClient")
def test_upsert_bumps_updated_at_and_persists(mock_cosmos_client: MagicMock) -> None:
    store = CosmosSessionStore(make_settings())
    store.start()

    record = SessionRecord(session_id="abc-123")
    original_updated_at = record.updated_at

    result = store.upsert(record)

    assert result.updated_at != original_updated_at
    store._container.upsert_item.assert_called_once()


@patch("app.infrastructure.session_store.CosmosClient")
def test_upsert_writes_unconditionally_when_the_record_has_no_etag(
    mock_cosmos_client: MagicMock,
) -> None:
    """A record that never round-tripped through Cosmos (no ``etag``) must
    not accidentally pass ``etag=None`` as an if-match condition — that
    writes unconditionally, same as before optimistic concurrency existed."""
    store = CosmosSessionStore(make_settings())
    store.start()

    store.upsert(SessionRecord(session_id="abc-123"))

    kwargs = store._container.upsert_item.call_args.kwargs
    assert "etag" not in kwargs
    assert "match_condition" not in kwargs


@patch("app.infrastructure.session_store.CosmosClient")
def test_upsert_passes_the_records_etag_as_an_if_match_condition(
    mock_cosmos_client: MagicMock,
) -> None:
    store = CosmosSessionStore(make_settings())
    store.start()
    record = SessionRecord(session_id="abc-123")
    record.etag = '"etag-1"'

    store.upsert(record)

    kwargs = store._container.upsert_item.call_args.kwargs
    assert kwargs["etag"] == '"etag-1"'
    assert kwargs["match_condition"] is MatchConditions.IfNotModified


@patch("app.infrastructure.session_store.CosmosClient")
def test_upsert_captures_the_new_etag_after_a_successful_write(
    mock_cosmos_client: MagicMock,
) -> None:
    store = CosmosSessionStore(make_settings())
    store.start()
    store._container.upsert_item.return_value = {"id": "abc-123", "_etag": '"etag-2"'}
    record = SessionRecord(session_id="abc-123")
    record.etag = '"etag-1"'

    result = store.upsert(record)

    assert result.etag == '"etag-2"'


@patch("app.infrastructure.session_store.CosmosClient")
def test_upsert_raises_session_conflict_error_on_an_etag_mismatch(
    mock_cosmos_client: MagicMock,
) -> None:
    """A concurrent writer changing the session in between (Cosmos 412,
    ``CosmosAccessConditionFailedError``) must surface as the store's own
    ``SessionConflictError`` — a caller (the web routes) can catch that
    without knowing anything about Cosmos or ETags."""
    store = CosmosSessionStore(make_settings())
    store.start()
    store._container.upsert_item.side_effect = (
        CosmosAccessConditionFailedError()  # type: ignore[no-untyped-call]
    )
    record = SessionRecord(session_id="abc-123")
    record.etag = '"stale-etag"'

    try:
        store.upsert(record)
    except SessionConflictError:
        pass
    else:
        raise AssertionError("Expected SessionConflictError on an ETag mismatch.")


@patch("app.infrastructure.session_store.CosmosClient")
def test_list_for_owner_returns_empty_for_a_falsy_owner_oid(
    mock_cosmos_client: MagicMock,
) -> None:
    """No querying at all for an unowned/anonymous caller — matches
    ownership.py's "unowned records are nobody's" rule."""
    store = CosmosSessionStore(make_settings())
    store.start()

    assert store.list_for_owner("") == []
    store._container.query_items.assert_not_called()


@patch("app.infrastructure.session_store.CosmosClient")
def test_list_for_owner_queries_cross_partition_and_validates_results(
    mock_cosmos_client: MagicMock,
) -> None:
    store = CosmosSessionStore(make_settings())
    store.start()
    store._container.query_items.return_value = [
        {
            "id": "abc-123",
            "session_id": "abc-123",
            "owner_oid": "owner-1",
            "_etag": '"etag-1"',
        },
        {"id": "def-456", "session_id": "def-456", "owner_oid": "owner-1"},
    ]

    records = store.list_for_owner("owner-1")

    assert [r.session_id for r in records] == ["abc-123", "def-456"]
    assert records[0].etag == '"etag-1"'
    store._container.query_items.assert_called_once_with(
        query="SELECT * FROM c WHERE c.owner_oid = @owner ORDER BY c._ts DESC",
        parameters=[{"name": "@owner", "value": "owner-1"}],
        enable_cross_partition_query=True,
    )


def test_close_is_a_noop_before_start_is_called() -> None:
    store = CosmosSessionStore(make_settings())

    store.close()  # must not raise, even though start() never ran


def test_close_does_not_call_anything_on_the_client() -> None:
    """Regression test: the synchronous ``azure.cosmos.CosmosClient`` has no
    ``close()`` method — only ``azure.cosmos.aio.CosmosClient`` does. A plain
    ``MagicMock()`` would silently accept a wrongly-called ``.close()`` here
    and hide that mismatch, so this uses ``spec=CosmosClient`` to make an
    invalid call fail the way it would against the real SDK.
    """
    store = CosmosSessionStore(make_settings())
    store._client = MagicMock(spec=CosmosClient)

    store.close()

    assert store._client.method_calls == []
