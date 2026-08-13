from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.web.main import create_app

# Every test above constructs TestClient(app) and calls .get() directly,
# which — deliberately, so none of them need real Entra ID credentials —
# never runs the app's `lifespan` (startup/shutdown only fire when
# TestClient is used as a context manager: `with TestClient(app) as c:`).
# That's exactly why the "sync CosmosClient has no close()" bug shipped
# without a failing test: nothing here ever exercised shutdown. The tests
# below close that gap by using the context-manager form specifically.


def make_app(**settings_overrides: object) -> TestClient:
    settings = Settings.model_validate(settings_overrides)
    with patch("app.web.main.get_settings", return_value=settings):
        app = create_app()
    # /me and require_user both call get_settings() again at request time —
    # patch it for the lifetime of the returned client too.
    patcher = patch("app.security.auth.get_settings", return_value=settings)
    patcher.start()
    client = TestClient(app)
    client._settings_patcher = patcher  # type: ignore[attr-defined]
    return client


def test_health_is_reachable_without_auth() -> None:
    client = make_app(auth_enabled=True, entra_tenant_id="t", entra_client_id="c")
    try:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    finally:
        client._settings_patcher.stop()  # type: ignore[attr-defined]


def test_me_returns_anonymous_when_auth_disabled() -> None:
    client = make_app(auth_enabled=False)
    try:
        response = client.get("/me")
        assert response.status_code == 200
        body = response.json()
        assert body["authenticated"] is False
        assert body["principal"] == "anonymous"
    finally:
        client._settings_patcher.stop()  # type: ignore[attr-defined]


def test_me_rejects_missing_token_when_auth_enabled() -> None:
    client = make_app(auth_enabled=True, entra_tenant_id="t", entra_client_id="c")
    try:
        response = client.get("/me")
        assert response.status_code == 401
    finally:
        client._settings_patcher.stop()  # type: ignore[attr-defined]


def test_me_returns_claims_when_token_valid() -> None:
    client = make_app(auth_enabled=True, entra_tenant_id="t", entra_client_id="c")
    try:
        with patch(
            "app.security.auth.decode_token",
            return_value={
                "oid": "abc-123",
                "preferred_username": "vaibhav@example.com",
            },
        ):
            response = client.get("/me", headers={"Authorization": "Bearer a.b.c"})

        assert response.status_code == 200
        body = response.json()
        assert body["authenticated"] is True
        assert body["principal"] == "vaibhav@example.com"
        assert body["oid"] == "abc-123"
    finally:
        client._settings_patcher.stop()  # type: ignore[attr-defined]


@patch("app.web.main.ArtifactStore", autospec=True)
@patch("app.web.main.CosmosSessionStore", autospec=True)
def test_lifespan_starts_and_closes_both_stores(
    mock_session_store_cls: object,
    mock_artifact_store_cls: object,
) -> None:
    settings = Settings(auth_enabled=False)
    with patch("app.web.main.get_settings", return_value=settings):
        app = create_app()

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200

    session_store = mock_session_store_cls.return_value  # type: ignore[attr-defined]
    artifact_store = mock_artifact_store_cls.return_value  # type: ignore[attr-defined]
    session_store.start.assert_called_once()
    session_store.close.assert_called_once()
    artifact_store.close.assert_called_once()


@patch("app.web.main.ArtifactStore", autospec=True)
@patch("app.web.main.CosmosSessionStore", autospec=True)
def test_lifespan_still_closes_artifact_store_when_session_store_close_fails(
    mock_session_store_cls: object,
    mock_artifact_store_cls: object,
) -> None:
    """One store failing to close must not stop the other from closing, and
    must not turn a normal shutdown into an unhandled exception — see the
    `for name, close in (...)` loop in `lifespan`."""
    mock_session_store_cls.return_value.close.side_effect = RuntimeError(  # type: ignore[attr-defined]
        "boom"
    )

    settings = Settings(auth_enabled=False)
    with patch("app.web.main.get_settings", return_value=settings):
        app = create_app()

    with TestClient(app) as client:
        client.get("/health")

    artifact_store = mock_artifact_store_cls.return_value  # type: ignore[attr-defined]
    artifact_store.close.assert_called_once()
