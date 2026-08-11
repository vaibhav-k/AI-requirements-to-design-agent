from unittest.mock import Mock

from app.storage import ArtifactStore


def test_latest_design_version() -> None:
    store = object.__new__(ArtifactStore)

    blob_1 = Mock()
    blob_1.name = "dev/session-1/design/v1.json"

    blob_2 = Mock()
    blob_2.name = "dev/session-1/design/v2.json"

    blob_3 = Mock()
    blob_3.name = "dev/session-1/design/v3.svg"

    blob_other = Mock()
    blob_other.name = "dev/session-2/design/v9.json"

    container = Mock()

    container.list_blobs.return_value = [
        blob_1,
        blob_2,
        blob_3,
        blob_other,
    ]

    store.container = container
    store.environment = "dev"

    assert store.get_latest_design_version("session-1") == 2
