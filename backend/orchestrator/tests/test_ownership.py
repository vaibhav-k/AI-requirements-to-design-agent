from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.api.ownership import is_admin, owns
from app.config import Settings
from app.domain.session import SessionRecord


def make_request(user: dict[str, object] | None = None) -> MagicMock:
    request = MagicMock()
    request.state = MagicMock()
    request.state.user = user
    return request


def test_is_admin_is_false_when_auth_disabled() -> None:
    settings = Settings(auth_enabled=False)
    request = make_request(user={"oid": "abc", "roles": ["Admin"]})

    with patch("app.api.ownership.get_settings", return_value=settings):
        assert is_admin(request) is False


def test_is_admin_is_true_for_a_caller_with_the_admin_role() -> None:
    settings = Settings(auth_enabled=True)
    request = make_request(user={"oid": "abc", "roles": ["Admin"]})

    with patch("app.api.ownership.get_settings", return_value=settings):
        assert is_admin(request) is True


def test_is_admin_is_false_for_a_caller_without_the_admin_role() -> None:
    settings = Settings(auth_enabled=True)
    request = make_request(user={"oid": "abc", "roles": ["User"]})

    with patch("app.api.ownership.get_settings", return_value=settings):
        assert is_admin(request) is False


def test_owns_bypasses_ownership_for_an_admin() -> None:
    settings = Settings(auth_enabled=True)
    record = SessionRecord(session_id="s-1", owner_oid="someone-else")
    request = make_request(user={"oid": "caller-1", "roles": ["Admin"]})

    with patch("app.api.ownership.get_settings", return_value=settings):
        assert owns(record, request) is True


def test_owns_still_denies_a_non_admin_reading_someone_elses_session() -> None:
    settings = Settings(auth_enabled=True)
    record = SessionRecord(session_id="s-1", owner_oid="someone-else")
    request = make_request(user={"oid": "caller-1", "roles": ["User"]})

    with patch("app.api.ownership.get_settings", return_value=settings):
        assert owns(record, request) is False
