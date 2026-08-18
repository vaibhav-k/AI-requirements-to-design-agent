from __future__ import annotations

from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.config import Settings
from app.security.auth import (
    ROLE_ADMIN,
    ROLE_ARCHITECT,
    ROLE_USER,
    AuthError,
    RoleError,
    current_claims,
    current_roles,
    current_user_key,
    decode_token,
    principal_of,
    require_role,
    require_user,
    roles_of,
    user_key,
    valid_audiences,
    valid_issuers,
)


def make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "auth_enabled": True,
        "entra_tenant_id": "tenant-123",
        "entra_client_id": "client-456",
    }
    defaults.update(overrides)
    return Settings.model_validate(defaults)


def make_request(user: dict[str, object] | None = None) -> MagicMock:
    """A minimal stand-in for FastAPI's Request, carrying request.state.user."""

    request = MagicMock()
    request.state = MagicMock()
    request.state.user = user
    return request


# --------------------------------------------------------------------------- #
# principal_of / user_key
# --------------------------------------------------------------------------- #


def test_principal_of_prefers_preferred_username() -> None:
    claims = {"preferred_username": "vaibhav@example.com", "oid": "abc"}
    assert principal_of(claims) == "vaibhav@example.com"


def test_principal_of_falls_back_through_claim_order() -> None:
    assert principal_of({"oid": "abc"}) == "abc"
    assert principal_of({"sub": "xyz"}) == "xyz"


def test_principal_of_returns_unknown_when_no_claims_present() -> None:
    assert principal_of({}) == "unknown"


def test_user_key_prefers_oid_over_sub() -> None:
    assert user_key({"oid": "abc", "sub": "xyz"}) == "abc"


def test_user_key_falls_back_to_sub() -> None:
    assert user_key({"sub": "xyz"}) == "xyz"


def test_user_key_is_none_when_neither_claim_present() -> None:
    assert user_key({}) is None


# --------------------------------------------------------------------------- #
# valid_issuers / valid_audiences
# --------------------------------------------------------------------------- #


def test_valid_issuers_includes_v2_and_legacy_sts() -> None:
    issuers = valid_issuers("tenant-123")
    assert "https://login.microsoftonline.com/tenant-123/v2.0" in issuers
    assert "https://sts.windows.net/tenant-123/" in issuers


def test_valid_audiences_includes_bare_and_api_prefixed() -> None:
    audiences = valid_audiences("client-456")
    assert "client-456" in audiences
    assert "api://client-456" in audiences


# --------------------------------------------------------------------------- #
# current_claims / current_user_key
# --------------------------------------------------------------------------- #


def test_current_claims_returns_attached_user_state() -> None:
    request = make_request(user={"oid": "abc"})
    assert current_claims(request) == {"oid": "abc"}


def test_current_claims_returns_empty_dict_when_unset() -> None:
    request = make_request(user=None)
    assert current_claims(request) == {}


def test_current_user_key_reads_through_current_claims() -> None:
    request = make_request(user={"oid": "abc"})
    assert current_user_key(request) == "abc"


# --------------------------------------------------------------------------- #
# decode_token
# --------------------------------------------------------------------------- #


def test_decode_token_rejects_when_tenant_not_configured() -> None:
    settings = make_settings(entra_tenant_id="")

    with pytest.raises(AuthError):
        decode_token("some-token", settings)


@patch("app.security.auth._jwk_client")
@patch("app.security.auth.jwt.decode")
def test_decode_token_returns_claims_on_success(
    mock_decode: MagicMock,
    mock_jwk_client: MagicMock,
) -> None:
    settings = make_settings()
    signing_key = MagicMock()
    signing_key.key = "public-key"
    mock_jwk_client.return_value.get_signing_key_from_jwt.return_value = signing_key
    mock_decode.return_value = {"oid": "abc", "aud": "client-456"}

    claims = decode_token("a.b.c", settings)

    assert claims == {"oid": "abc", "aud": "client-456"}
    mock_decode.assert_called_once()


@patch("app.security.auth._jwk_client")
def test_decode_token_wraps_expired_signature_as_auth_error(
    mock_jwk_client: MagicMock,
) -> None:
    settings = make_settings()
    signing_key = MagicMock()
    signing_key.key = "public-key"
    mock_jwk_client.return_value.get_signing_key_from_jwt.return_value = signing_key

    with patch(
        "app.security.auth.jwt.decode",
        side_effect=jwt.ExpiredSignatureError("expired"),
    ):
        with pytest.raises(AuthError):
            decode_token("a.b.c", settings)


@patch("app.security.auth._jwk_client")
def test_decode_token_wraps_bad_audience_as_auth_error(
    mock_jwk_client: MagicMock,
) -> None:
    settings = make_settings()
    signing_key = MagicMock()
    signing_key.key = "public-key"
    mock_jwk_client.return_value.get_signing_key_from_jwt.return_value = signing_key

    with patch(
        "app.security.auth.jwt.decode",
        side_effect=jwt.InvalidAudienceError("bad audience"),
    ):
        with pytest.raises(AuthError):
            decode_token("a.b.c", settings)


@patch("app.security.auth._jwk_client")
def test_decode_token_wraps_malformed_token_as_auth_error(
    mock_jwk_client: MagicMock,
) -> None:
    settings = make_settings()
    mock_jwk_client.return_value.get_signing_key_from_jwt.side_effect = jwt.DecodeError(
        "not a token"
    )

    with pytest.raises(AuthError):
        decode_token("garbage", settings)


# --------------------------------------------------------------------------- #
# require_user
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_require_user_is_noop_when_auth_disabled() -> None:
    settings = make_settings(auth_enabled=False)
    request = make_request()

    with patch("app.security.auth.get_settings", return_value=settings):
        claims = await require_user(request, credentials=None)

    assert claims == {}


@pytest.mark.asyncio
async def test_require_user_rejects_missing_credentials_when_enabled() -> None:
    settings = make_settings()
    request = make_request()

    with patch("app.security.auth.get_settings", return_value=settings):
        with pytest.raises(HTTPException) as exc_info:
            await require_user(request, credentials=None)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_user_attaches_claims_to_request_state_on_success() -> None:
    settings = make_settings()
    request = make_request()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="a.b.c")

    with (
        patch("app.security.auth.get_settings", return_value=settings),
        patch(
            "app.security.auth.decode_token",
            return_value={"oid": "abc"},
        ),
    ):
        claims = await require_user(request, credentials=credentials)

    assert claims == {"oid": "abc"}
    assert request.state.user == {"oid": "abc"}


# --------------------------------------------------------------------------- #
# roles_of / current_roles
# --------------------------------------------------------------------------- #


def test_roles_of_reads_the_roles_claim() -> None:
    assert roles_of({"roles": ["Architect", "User"]}) == {"Architect", "User"}


def test_roles_of_is_empty_when_claim_missing() -> None:
    assert roles_of({}) == frozenset()


def test_roles_of_is_empty_when_claim_is_not_a_list() -> None:
    assert roles_of({"roles": "Architect"}) == frozenset()


def test_current_roles_reads_through_current_claims() -> None:
    request = make_request(user={"oid": "abc", "roles": ["Reviewer"]})
    assert current_roles(request) == {"Reviewer"}


# --------------------------------------------------------------------------- #
# require_role
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_require_role_is_a_noop_when_auth_disabled() -> None:
    settings = make_settings(auth_enabled=False)

    with patch("app.security.auth.get_settings", return_value=settings):
        roles = await require_role(ROLE_ARCHITECT)({})

    assert ROLE_ARCHITECT in roles


@pytest.mark.asyncio
async def test_require_role_allows_a_caller_with_an_allowed_role() -> None:
    settings = make_settings(auth_enabled=True)

    with patch("app.security.auth.get_settings", return_value=settings):
        roles = await require_role(ROLE_USER, ROLE_ARCHITECT)({"roles": [ROLE_USER]})

    assert roles == {ROLE_USER}


@pytest.mark.asyncio
async def test_require_role_rejects_a_caller_without_an_allowed_role() -> None:
    settings = make_settings(auth_enabled=True)

    with patch("app.security.auth.get_settings", return_value=settings):
        with pytest.raises(RoleError) as exc_info:
            await require_role(ROLE_ARCHITECT)({"roles": [ROLE_USER]})

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_role_rejects_a_caller_with_no_roles_at_all() -> None:
    settings = make_settings(auth_enabled=True)

    with patch("app.security.auth.get_settings", return_value=settings):
        with pytest.raises(RoleError):
            await require_role(ROLE_USER, ROLE_ARCHITECT)({})


@pytest.mark.asyncio
async def test_require_role_always_allows_admin_regardless_of_allowed_roles() -> None:
    settings = make_settings(auth_enabled=True)

    with patch("app.security.auth.get_settings", return_value=settings):
        roles = await require_role(ROLE_ARCHITECT)({"roles": [ROLE_ADMIN]})

    assert roles == {ROLE_ADMIN}
