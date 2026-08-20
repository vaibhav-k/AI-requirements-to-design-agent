"""Entra ID (Azure AD) bearer-token authentication for the web API.

Validates the ``Authorization: Bearer <token>`` header on incoming requests
against the tenant's published signing keys (JWKS): no client secret is
needed to *validate* a token - only to acquire one - so this stays purely
a resource-server concern.

Authentication is opt-in via ``Settings.auth_enabled``. With it left off (the
default), ``require_user`` is a no-op that returns an empty claims dict, so
local development and CI never need a real Entra ID tenant configured.

This module also implements role-based access control (RBAC) on top of that
authentication: ``require_role`` reads the Entra ID App Roles on the
validated token (the standard ``roles`` claim - see ``roles_of``) and gates
a route to callers holding one of a set of allowed roles. See the README's
"RBAC" section for the app-role setup (App registration → App roles →
Enterprise Applications assignment) and the permission matrix
(User/Architect/Reviewer/Admin) this project uses.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

ALGORITHMS = ["RS256"]


def _jwks_uri(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"


@lru_cache(maxsize=4)
def _jwk_client(tenant_id: str) -> PyJWKClient:
    """One key client per tenant, cached - it keeps the fetched keys in memory."""
    return PyJWKClient(_jwks_uri(tenant_id), cache_keys=True)


def valid_issuers(tenant_id: str) -> tuple[str, ...]:
    return (
        f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        f"https://sts.windows.net/{tenant_id}/",
    )


def valid_audiences(client_id: str) -> tuple[str, ...]:
    return (client_id, f"api://{client_id}")


class AuthError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


def decode_token(token: str, settings: Settings) -> dict[str, Any]:
    if not settings.entra_tenant_id or not settings.entra_client_id:
        raise AuthError(
            "Authentication is enabled but ENTRA_TENANT_ID / "
            "ENTRA_CLIENT_ID are not configured."
        )

    try:
        signing_key = _jwk_client(settings.entra_tenant_id).get_signing_key_from_jwt(
            token
        )
    except jwt.DecodeError as exc:
        logger.info("Rejected a malformed bearer token: %s", exc)
        raise AuthError(f"Token is not valid: {exc}") from exc
    except Exception as exc:
        logger.warning("Could not resolve the token's signing key", exc_info=True)
        raise AuthError(f"Token signing key could not be resolved: {exc}") from exc

    try:
        decoded: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=ALGORITHMS,
            audience=list(valid_audiences(settings.entra_client_id)),
            issuer=list(valid_issuers(settings.entra_tenant_id)),
            options={"require": ["exp", "iss", "aud"]},
        )
        return decoded
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Token has expired.") from exc
    except jwt.InvalidAudienceError as exc:
        raise AuthError(
            "Token audience does not match this API. The client must send a "
            f"token for client {settings.entra_client_id} - a token for "
            "Microsoft Graph or another resource is rejected here."
        ) from exc
    except jwt.InvalidIssuerError as exc:
        raise AuthError("Token was issued by a different directory.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError(f"Token is not valid: {exc}") from exc


def principal_of(claims: dict[str, Any]) -> str:
    """A human-readable identity for logs, from whichever claim is present."""
    for key in ("preferred_username", "upn", "email", "unique_name", "oid", "sub"):
        value = claims.get(key)
        if value:
            return str(value)
    return "unknown"


def user_key(claims: dict[str, Any]) -> str | None:
    """The stable identifier an artifact/session should be owned by.

    ``oid`` - the user's immutable object id in the directory - not
    ``preferred_username``/``upn``, which change when someone's email or
    surname does and would orphan their history. ``sub`` is the fallback:
    also stable, but pairwise per-application, so it only matches within
    this app.
    """
    return claims.get("oid") or claims.get("sub") or None


def current_claims(request: Request) -> dict[str, Any]:
    """Claims attached by :func:`require_user`, or empty when auth is disabled."""
    return getattr(request.state, "user", None) or {}


def current_user_key(request: Request) -> str | None:
    return user_key(current_claims(request))


async def require_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),  # noqa: B008
) -> dict[str, Any]:
    """FastAPI dependency: attach validated claims to ``request.state.user``.

    Add ``dependencies=[Depends(require_user)]`` to a router (or a single
    route) to require a valid Entra ID bearer token for every request it
    handles.
    """
    settings = get_settings()
    if not settings.auth_enabled:
        return {}

    if credentials is None or not credentials.credentials:
        raise AuthError(
            "Missing bearer token. You are not signed in - sign in and "
            "retry with a valid Entra ID access token in the "
            "Authorization header."
        )

    claims = decode_token(credentials.credentials, settings)
    request.state.user = claims
    return claims


# --------------------------------------------------------------------------- #
# RBAC - Entra ID App Roles
# --------------------------------------------------------------------------- #

# Defined in the app registration's "App roles" manifest blade and assigned
# to users/groups under Enterprise Applications → this app → Users and
# groups; Entra ID then populates the token's `roles` claim with whichever
# of these the signed-in caller was assigned. Not a hierarchy - a caller may
# hold more than one - except `ROLE_ADMIN`, which `require_role` always lets
# through regardless of which roles it was asked to check for (see below).
ROLE_ADMIN = "Admin"
ROLE_ARCHITECT = "Architect"
ROLE_REVIEWER = "Reviewer"
ROLE_USER = "User"

ALL_APP_ROLES = (ROLE_ADMIN, ROLE_ARCHITECT, ROLE_REVIEWER, ROLE_USER)


def roles_of(claims: dict[str, Any]) -> frozenset[str]:
    """The Entra ID App Roles on a decoded token, or empty if none.

    Reads the standard ``roles`` claim (a JSON array of strings that Entra
    ID populates from Enterprise Applications role assignments) - not
    ``scp`` (delegated *scopes*, the audience/permission concept
    ``decode_token`` already validates) and not ``wids``/``groups`` (built-in
    directory roles / security group membership) - App Roles are what this
    project's RBAC is built on; see the README's "RBAC" section for why.
    """
    raw = claims.get("roles", [])
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(str(role) for role in raw)


def current_roles(request: Request) -> frozenset[str]:
    """The caller's App Roles, read through ``current_claims``."""
    return roles_of(current_claims(request))


class RoleError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def require_role(
    *allowed: str,
) -> Callable[[dict[str, Any]], Awaitable[frozenset[str]]]:
    """FastAPI dependency factory: 403 unless the caller holds one of ``allowed``.

    ``ROLE_ADMIN`` always passes, no matter what ``allowed`` was asked for -
    "Admins can manage users and access across the system" (see the
    README's "RBAC" section) means Admin is a superset of every other
    role's permissions, not a fifth, separately-granted capability. A caller
    with no recognized role at all - including one with a perfectly valid
    token - always fails, even a bare ``require_role(*ALL_APP_ROLES)`` on a
    read-only route: an authenticated user who was never assigned an app
    role gets 403, not silent full access, matching this project's decision
    to reject rather than default such a caller into the baseline role.

    A no-op when ``Settings.auth_enabled`` is ``False``, exactly like
    ``require_user`` - local development and CI never need roles
    configured either, only a real Entra ID tenant with AUTH_ENABLED=true
    does.
    """

    async def _dependency(
        claims: dict[str, Any] = Depends(require_user),  # noqa: B008
    ) -> frozenset[str]:
        settings = get_settings()
        if not settings.auth_enabled:
            return frozenset(ALL_APP_ROLES)

        roles = roles_of(claims)
        if ROLE_ADMIN in roles or roles & set(allowed):
            return roles

        raise RoleError(
            "This action requires one of these roles: "
            f"{', '.join(sorted(allowed))}. "
            f"Caller has: {', '.join(sorted(roles)) or 'none'}."
        )

    return _dependency
