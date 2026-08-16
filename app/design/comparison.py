"""Backend-computed structured comparison between two architecture versions.

The frontend already does this client-side (`frontend/src/lib/diff.ts`'s
`diffByKey`, consumed by `ArchitectureView.tsx`) — pick two persisted
versions and diff them in the browser. This module is the server-side
equivalent: the same id-keyed added/removed/changed/unchanged shape,
computed once here so any client (this frontend, another UI, an MCP
client) can get a diff without re-implementing the comparison logic
itself, exposed via `GET /requirements-runs/{id}/architecture/compare`
(`app/api/routes/artifacts.py`).

Equality is structural (`model_dump()` equality on two Pydantic models of
the same type), the same approach `diffByKey` uses (JSON-stringify) — this
is sufficient because both versions being compared are the same
`SystemDesignArtifact` schema; there's no cross-version schema migration to
account for.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

from app.design.models import (
    DesignAssumption,
    DesignComponent,
    DesignInterface,
    DesignQuestion,
    ExternalDependency,
    SystemDesignArtifact,
)

T = TypeVar("T", bound=BaseModel)


class ListDiffChange(BaseModel, Generic[T]):
    """One item present in both versions, but with different content."""

    before: T
    after: T


class ListDiff(BaseModel, Generic[T]):
    """Added/removed/changed/unchanged items between two id-keyed lists."""

    added: list[T]
    removed: list[T]
    changed: list[ListDiffChange[T]]
    unchanged: list[T]


def _diff_by_id(before: list[T], after: list[T]) -> ListDiff[T]:
    """Generic id-keyed list diff — mirrors `diffByKey` in
    `frontend/src/lib/diff.ts`. Every model diffed here (`DesignComponent`,
    `DesignInterface`, `ExternalDependency`, `DesignAssumption`,
    `DesignQuestion`) has an `id: str` field, so this can stay generic
    instead of needing a bespoke comparator per field.
    """

    before_by_id = {item.id: item for item in before}  # type: ignore[attr-defined]
    after_by_id = {item.id: item for item in after}  # type: ignore[attr-defined]

    added: list[T] = []
    changed: list[ListDiffChange[T]] = []
    unchanged: list[T] = []

    for item_id, after_item in after_by_id.items():
        before_item = before_by_id.get(item_id)
        if before_item is None:
            added.append(after_item)
        elif before_item.model_dump() != after_item.model_dump():
            changed.append(ListDiffChange(before=before_item, after=after_item))
        else:
            unchanged.append(after_item)

    removed = [
        before_item
        for item_id, before_item in before_by_id.items()
        if item_id not in after_by_id
    ]

    return ListDiff(added=added, removed=removed, changed=changed, unchanged=unchanged)


class ArchitectureComparison(BaseModel):
    """Structured diff between two versions of the same session's architecture."""

    from_version: int
    to_version: int

    architecture_summary_changed: bool
    from_architecture_summary: str
    to_architecture_summary: str

    components: ListDiff[DesignComponent]
    interfaces: ListDiff[DesignInterface]
    external_dependencies: ListDiff[ExternalDependency]
    assumptions: ListDiff[DesignAssumption]
    open_questions: ListDiff[DesignQuestion]


def compare_architectures(
    from_version: int,
    to_version: int,
    before: SystemDesignArtifact,
    after: SystemDesignArtifact,
) -> ArchitectureComparison:
    """Compute the structured diff between two architecture versions."""

    return ArchitectureComparison(
        from_version=from_version,
        to_version=to_version,
        architecture_summary_changed=(
            before.architecture_summary != after.architecture_summary
        ),
        from_architecture_summary=before.architecture_summary,
        to_architecture_summary=after.architecture_summary,
        components=_diff_by_id(before.components, after.components),
        interfaces=_diff_by_id(before.interfaces, after.interfaces),
        external_dependencies=_diff_by_id(
            before.external_dependencies, after.external_dependencies
        ),
        assumptions=_diff_by_id(before.assumptions, after.assumptions),
        open_questions=_diff_by_id(before.open_questions, after.open_questions),
    )
