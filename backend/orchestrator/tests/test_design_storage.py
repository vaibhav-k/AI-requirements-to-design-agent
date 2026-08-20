from unittest.mock import Mock

from azure.core.exceptions import ResourceNotFoundError

from app.infrastructure.artifact_store import ArtifactStore


def make_store(blobs: list[Mock]) -> ArtifactStore:
    store = object.__new__(ArtifactStore)
    container = Mock()
    container.list_blobs.return_value = blobs
    store.container = container
    store.environment = "dev"
    return store


def make_blob(name: str) -> Mock:
    blob = Mock()
    blob.name = name
    return blob


def test_latest_design_version() -> None:
    store = make_store(
        [
            make_blob("dev/session-1/design/v1.json"),
            make_blob("dev/session-1/design/v2.json"),
            make_blob("dev/session-1/design/v3.svg"),
            make_blob("dev/session-2/design/v9.json"),
        ]
    )

    assert store.get_latest_design_version("session-1") == 2


def test_latest_design_version_is_zero_when_none_exist() -> None:
    store = make_store([])

    assert store.get_latest_design_version("session-1") == 0


def test_list_design_versions_returns_json_versions_sorted_ascending() -> None:
    """SVGs and other sessions' blobs must not leak into the version list -
    only this session's own design *JSON* versions count."""
    store = make_store(
        [
            make_blob("dev/session-1/design/v3.json"),
            make_blob("dev/session-1/design/v1.json"),
            make_blob("dev/session-1/design/v2.json"),
            make_blob("dev/session-1/design/v2.svg"),
            make_blob("dev/session-2/design/v9.json"),
        ]
    )

    assert store.list_design_versions("session-1") == [1, 2, 3]


def test_list_requirements_versions_returns_json_versions_sorted_ascending() -> None:
    store = make_store(
        [
            make_blob("dev/session-1/requirements/v2.json"),
            make_blob("dev/session-1/requirements/v1.json"),
            make_blob("dev/session-2/requirements/v9.json"),
        ]
    )

    assert store.list_requirements_versions("session-1") == [1, 2]


def test_get_requirements_json_returns_the_blob_content() -> None:
    store = object.__new__(ArtifactStore)
    container = Mock()
    blob_client = Mock()
    blob_client.download_blob.return_value.readall.return_value = b'{"summary": "x"}'
    container.get_blob_client.return_value = blob_client
    store.container = container
    store.environment = "dev"

    result = store.get_requirements_json("session-1", 1)

    assert result == '{"summary": "x"}'
    container.get_blob_client.assert_called_once_with(
        "dev/session-1/requirements/v1.json"
    )


def test_get_requirements_json_returns_none_when_missing() -> None:
    store = object.__new__(ArtifactStore)
    container = Mock()
    container.get_blob_client.return_value.download_blob.side_effect = (
        ResourceNotFoundError()
    )
    store.container = container
    store.environment = "dev"

    assert store.get_requirements_json("session-1", 99) is None


def test_get_design_json_returns_the_blob_content() -> None:
    store = object.__new__(ArtifactStore)
    container = Mock()
    blob_client = Mock()
    blob_client.download_blob.return_value.readall.return_value = (
        b'{"architecture_summary": "x"}'
    )
    container.get_blob_client.return_value = blob_client
    store.container = container
    store.environment = "dev"

    result = store.get_design_json("session-1", 2)

    assert result == '{"architecture_summary": "x"}'
    container.get_blob_client.assert_called_once_with("dev/session-1/design/v2.json")


def test_get_design_svg_returns_the_blob_content() -> None:
    store = object.__new__(ArtifactStore)
    container = Mock()
    blob_client = Mock()
    blob_client.download_blob.return_value.readall.return_value = b"<svg></svg>"
    container.get_blob_client.return_value = blob_client
    store.container = container
    store.environment = "dev"

    result = store.get_design_svg("session-1", 2)

    assert result == "<svg></svg>"
    container.get_blob_client.assert_called_once_with("dev/session-1/design/v2.svg")


def test_get_design_svg_returns_none_when_missing() -> None:
    store = object.__new__(ArtifactStore)
    container = Mock()
    container.get_blob_client.return_value.download_blob.side_effect = (
        ResourceNotFoundError()
    )
    store.container = container
    store.environment = "dev"

    assert store.get_design_svg("session-1", 99) is None
