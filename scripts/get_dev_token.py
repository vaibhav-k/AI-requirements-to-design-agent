"""
Get a real Entra ID access token for manually testing the web API.

Run it, sign in via the browser when prompted, and it prints an access
token you can paste into Swagger UI's "Authorize" dialog (the padlock icon
at http://127.0.0.1:8000/docs) or into an ``Authorization: Bearer <token>``
header directly.

This is a *testing convenience*, not part of the application. A real
frontend would use MSAL.js (or an equivalent) to sign users in and acquire
tokens the same way, automatically, on every request.

Usage:

    python scripts/get_dev_token.py

Requires, from your ``.env`` (same values the web API itself uses):

    ENTRA_TENANT_ID
    ENTRA_CLIENT_ID
    ENTRA_API_SCOPE     (defaults to "access_as_user")

It uses MSAL's device-code flow — a public-client flow that needs no
client secret — so your Entra ID app registration must have:

* An Application ID URI set (Expose an API blade), e.g. ``api://<client-id>``.
* A scope exposed under that URI matching ``ENTRA_API_SCOPE``
  (e.g. ``access_as_user``).
* "Allow public client flows" set to Yes (Authentication blade), since
  device-code sign-in is a public-client flow.

Without those, MSAL will fail — this script recognizes the common failure
codes (AADSTS7000218, AADSTS65001, AADSTS500011, AADSTS70011, AADSTS90002)
and prints which Portal setting fixes each one; see README.md's "Entra ID
App Registration Setup" section for the full walkthrough.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Running this file directly (``python scripts/get_dev_token.py``) only puts
# ``scripts/`` on sys.path, not the project root — so ``import app...`` fails
# with "No module named 'app'" unless the root is added explicitly here.
# (Running it as a module, ``python -m scripts.get_dev_token`` from the
# project root, wouldn't need this, but would need scripts/__init__.py.)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import msal  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402

load_dotenv()


# Maps an AADSTS error *code* (the numeric "AADSTSxxxxx" prefix Azure AD puts
# in error_description) to a one-line pointer at the specific Portal setting
# that fixes it. Keeps this script from just echoing Azure's often-oblique
# error text back at you — see README.md's "Entra ID App Registration Setup"
# section for the full walkthrough of each setting.
_KNOWN_ERROR_HINTS = {
    "AADSTS7000218": (
        "Your app registration requires a client secret, but device-code "
        "sign-in is a public-client flow that sends none. Fix: Authentication "
        "blade -> Advanced settings -> 'Allow public client flows' -> Yes."
    ),
    "AADSTS65001": (
        "Nobody has consented to this app requesting its own exposed scope "
        "yet. Fix: API permissions blade -> Add a permission -> My APIs -> "
        "select this same app -> Delegated permissions -> your scope -> Add, "
        "then 'Grant admin consent' (or sign in interactively once and accept "
        "the consent prompt)."
    ),
    "AADSTS500011": (
        "The resource ('api://<client-id>') wasn't found in this tenant. "
        "Fix: Expose an API blade -> set an Application ID URI -> Save."
    ),
    "AADSTS70011": (
        "The requested scope isn't recognized. Fix: Expose an API blade -> "
        "Add a scope -> name it to match ENTRA_API_SCOPE in .env."
    ),
    "AADSTS90002": (
        "Tenant not found. Fix: double-check ENTRA_TENANT_ID in .env against "
        "the app registration's Overview page."
    ),
}


def _explain(error_description: str | None) -> str | None:
    for code, hint in _KNOWN_ERROR_HINTS.items():
        if error_description and code in error_description:
            return hint
    return None


def retrieve_settings() -> Settings | int:
    settings = get_settings()

    if not settings.entra_tenant_id or not settings.entra_client_id:
        print(
            "ENTRA_TENANT_ID and ENTRA_CLIENT_ID must be set in .env "
            "(the same values the web API validates tokens against).",
            file=sys.stderr,
        )
        return 1
    return settings


def main() -> int:
    settings = retrieve_settings()
    if isinstance(settings, int):
        return 1

    authority = f"https://login.microsoftonline.com/{settings.entra_tenant_id}"
    scope = f"api://{settings.entra_client_id}/{settings.entra_api_scope}"

    app = msal.PublicClientApplication(
        settings.entra_client_id,
        authority=authority,
    )

    flow = app.initiate_device_flow(scopes=[scope])
    if "user_code" not in flow:
        print(f"Failed to start device flow: {flow}", file=sys.stderr)
        return 1

    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        description = result.get("error_description")
        print(
            "Failed to acquire a token:\n"
            f"  error: {result.get('error')}\n"
            f"  error_description: {description}",
            file=sys.stderr,
        )
        hint = _explain(description)
        if hint:
            print(f"\nLikely fix: {hint}", file=sys.stderr)
        else:
            print(
                "\nSee README.md's 'Entra ID App Registration Setup' section "
                "for the required app registration settings.",
                file=sys.stderr,
            )
        return 1

    print(
        "\nAccess token (paste into Swagger UI's Authorize dialog, no "
        "'Bearer ' prefix):\n"
    )
    print(result["access_token"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
