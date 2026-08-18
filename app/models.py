"""Backward-compatible re-export shim — DEPRECATED, do not add to this file.

Every model that used to live here moved to ``app.domain.requirements``
as the first slice of the Clean Architecture migration (see README →
"Clean Architecture Migration"). New code should import from
``app.domain.requirements`` directly. This module exists only so the
many call sites that still do ``from app.models import ...``
(``app/storage.py``, ``app/api/routes/requirements.py``,
``app/mcp/server.py``, ``app/session.py``, most of ``tests/``) keep
working while they're migrated one at a time in later slices — it will
be deleted once no importer of ``app.models`` remains.
"""

from __future__ import annotations

from app.domain.requirements import (
    Actor,
    Assumption,
    OpenQuestion,
    Requirement,
    RequirementsArtifact,
    StoredArtifact,
)

__all__ = [
    "Actor",
    "Assumption",
    "OpenQuestion",
    "Requirement",
    "RequirementsArtifact",
    "StoredArtifact",
]
