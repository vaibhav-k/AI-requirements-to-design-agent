"""Per-user authorisation for session records.

Synchronous to match this project's session store. Authentication
(``require_user``) establishes *that* a caller is a valid user in the
tenant; this adds *which sessions they may see* — a session is stamped
with the Entra ``oid`` of whoever started it, and every read is checked
against the caller.

Two rules are deliberate:

* **404, never 403.** Telling an unauthorised caller "this exists but isn't
  yours" confirms a session id they should know nothing about. A miss and a
  denial are indistinguishable from outside.
* **Unowned records are nobody's.** A session written before ownership
  existed (or created while auth was disabled) has ``owner_oid`` unset;
  treating that as public would reopen exactly the gap this closes, so it
  fails closed.

Ownership is skipped entirely when ``AUTH_ENABLED=false``, because there is
no identity to attribute a session to.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request, status

from app.config import get_settings
from app.infrastructure.session_store import SessionRecord, SessionStore
from app.security.auth import current_claims, current_user_key, principal_of

logger = logging.getLogger(__name__)

NOT_FOUND = "Session not found."


def ownership_enforced() -> bool:
    return get_settings().auth_enabled


def owner_fields(request: Request) -> tuple[str | None, str | None]:
    """``(owner_oid, owner_name)`` to stamp on a newly created session."""
    claims = current_claims(request)
    key = current_user_key(request)
    return key, (principal_of(claims) if key else None)


def owns(record: SessionRecord, request: Request) -> bool:
    if not ownership_enforced():
        return True
    caller = current_user_key(request)
    return bool(caller) and record.owner_oid == caller


def require_owned(record: SessionRecord | None, request: Request) -> SessionRecord:
    """Return the record, or raise 404 if it is missing or not the caller's."""
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    if not owns(record, request):
        logger.warning(
            "Denied access to session %s (owner=%s) for %s",
            record.session_id,
            record.owner_oid or "unowned",
            current_user_key(request) or "anonymous",
        )
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return record


def load_owned(store: SessionStore, session_id: str, request: Request) -> SessionRecord:
    """Fetch a record and authorise it in one step — the call every route uses."""
    return require_owned(store.get(session_id), request)
