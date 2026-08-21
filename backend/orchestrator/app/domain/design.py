"""The architecture/design bounded context's entities.

Moved here, verbatim, from the former ``app/design/models.py`` as part
of the Clean Architecture migration (see README -> "Clean Architecture
Migration") - the same "pure entity, zero I/O" home
``app.domain.requirements`` already gives the requirements bounded
context's entities. Nothing here depends on Pydantic beyond what every
other domain module already accepts as a shared-kernel dependency (see
``app/domain/__init__.py``).

``app/design/models.py`` used to be a deprecated re-export shim over
this module, the same "strangler fig" shape ``app/models.py`` used for
``app.domain.requirements`` - it has since been deleted (see README ->
"Clean Architecture Migration" -> the slice that migrated every
remaining importer off both shims). Every module that used to import
``SystemDesignArtifact`` and friends from ``app.design.models``
(``app/design/analyzer.py``, ``app/design/validator.py``,
``app/design/diagram.py``, ``app/design/comparison.py``,
``app/design/session.py``, the API routes, the MCP server,
``app/main.py``, ``app/infrastructure/session_store.py``,
``app/vision.py``, and all of ``tests/``) now imports directly from
here.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DesignComponent(BaseModel):
    """A logical component in the high-level architecture."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    responsibility: str = Field(min_length=1)

    # A short group/category name (e.g. "Client & Identity", "Data
    # Platform") shared by every component that logically belongs
    # together. Optional and blank by default so existing designs (and
    # any code constructing a `DesignComponent` without it) keep working
    # unchanged; `ArchitectureDiagramGenerator` treats a blank domain as
    # its own single "Other Components" group rather than requiring one.
    # See `app/design/diagram.py` for how this drives per-domain
    # clustering in the rendered diagram.
    domain: str = Field(default="")

    # A technology-agnostic trust/security boundary this component sits
    # in (e.g. "Public", "DMZ", "Private", "Internal"). Deliberately NOT
    # an Azure-specific networking concept (VNet/subnet/Private Endpoint
    # live on `AzureServiceMapping.connectivity`/`.trust_zone` instead) -
    # this field is what the Logical Architecture Diagram uses to draw
    # trust boundaries without leaking any cloud-specific detail into an
    # otherwise technology-neutral diagram. "TBD" (the default) renders
    # as an explicit "unknown" rather than being silently omitted.
    trust_zone: str = Field(default="TBD")

    requirement_ids: list[str] = Field(default_factory=list)


class DesignInterface(BaseModel):
    """A logical interaction between two architecture components."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)

    # Either component/actor id may name a `DesignComponent.id` or an
    # `Actor.id` - an interface can now terminate at an external actor
    # (e.g. "End User" or a third-party caller), not only at another
    # internal component. See `ArchitectureValidator` for how both ID
    # spaces are checked.
    source_component: str = Field(min_length=1)
    target_component: str = Field(min_length=1)

    # "sync" (request/response, e.g. HTTPS/gRPC) or "async" (event/
    # message, e.g. publish/consume via a queue or topic) - drives both
    # the diagram's line style (solid vs dashed) and its edge label
    # convention (request/response vs publishes/consumes), per the
    # architecture-generation notation rules. Defaults to "sync" since
    # that's the more common interaction and keeps pre-existing designs
    # (generated before this field existed) rendering exactly as before.
    flow_type: str = Field(default="sync")

    requirement_ids: list[str] = Field(default_factory=list)


class ExternalDependency(BaseModel):
    """An external service or dependency used by the system."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)

    used_by_components: list[str] = Field(default_factory=list)


class Actor(BaseModel):
    """An external human or system actor that interacts with the
    architecture from OUTSIDE its boundary - an end user, an
    administrator, or a third-party system that calls INTO this system.

    The mirror image of `ExternalDependency` (a system this architecture
    calls OUT to): an `Actor` is who/what calls in, captured so the
    Logical Architecture Diagram can show real external
    users/systems and the data flows they initiate, per the
    architecture-generation requirements. An interface's
    `source_component`/`target_component` may reference an `Actor.id`
    exactly like a `DesignComponent.id`.
    """

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: str = Field(default="user")  # "user" | "external_system"
    description: str = Field(default="TBD")


class AzureServiceMapping(BaseModel):
    """Maps one logical component/actor/external dependency to its
    concrete Azure implementation.

    This is the explicit traceability link the Azure Service Mapping
    Diagram is built from: `component_id` must match a
    `components[].id`, `actors[].id`, or `external_dependencies[].id`
    elsewhere in this artifact, and the mapping diagram renders that
    same id on the corresponding node so a reviewer can go from either
    diagram to the other by id alone.
    """

    id: str = Field(min_length=1)
    component_id: str = Field(min_length=1)
    azure_service: str = Field(min_length=1)
    service_category: str = Field(default="TBD")
    rationale: str = Field(default="TBD")
    alternatives_considered: list[str] = Field(default_factory=list)

    # "public-endpoint" | "private-endpoint" | "vnet-internal" |
    # "internal-only" | "TBD" - lets the Azure Service Mapping Diagram
    # correctly distinguish a PaaS service reached via Private Endpoint
    # from one that's actually inside a VNet/subnet, per the
    # architecture-generation accuracy requirements.
    connectivity: str = Field(default="TBD")

    # "Public" | "DMZ" | "Private VNet" | "Internal" | "TBD".
    trust_zone: str = Field(default="TBD")


class SupportingAzureService(BaseModel):
    """An Azure service that supports the architecture but isn't itself
    a 1:1 mapping of one logical component - identity, networking,
    security, secrets, monitoring/logging, or CI/CD, per the
    architecture-generation requirement to include these even though no
    single logical component "is" them.
    """

    id: str = Field(min_length=1)
    azure_service: str = Field(min_length=1)
    # "Identity" | "Networking" | "Security" | "Secrets" | "Monitoring" |
    # "CI/CD" | "Other".
    category: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    rationale: str = Field(default="TBD")
    applies_to_components: list[str] = Field(default_factory=list)


class DiagramMetadata(BaseModel):
    """The metadata block required on every diagram.

    Built deterministically by code (see
    ``app/design/session.py``/``src/infrastructure/diagram.py``), never
    by the LLM - fields with no real value available default to "TBD"
    rather than being invented, per the architecture-generation
    requirement. Not part of the LLM-generated `SystemDesignArtifact`
    itself; this is a rendering-time value threaded alongside it.
    """

    title: str = Field(min_length=1)
    description: str = Field(default="TBD")
    scope: str = Field(default="TBD")
    author: str = Field(default="TBD")
    version: int = Field(default=1)
    last_updated: str = Field(default="TBD")
    external_references: list[str] = Field(default_factory=list)


class DesignAssumption(BaseModel):
    """An assumption made while creating the architecture."""

    id: str = Field(min_length=1)
    assumption: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class DesignQuestion(BaseModel):
    """An architecture question that remains unresolved."""

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class SystemDesignArtifact(BaseModel):
    """High-level system architecture generated from requirements."""

    architecture_summary: str = Field(min_length=1)

    components: list[DesignComponent] = Field(default_factory=list)

    interfaces: list[DesignInterface] = Field(default_factory=list)

    external_dependencies: list[ExternalDependency] = Field(default_factory=list)

    # External human/system actors that interact with the architecture -
    # feeds the Logical Architecture Diagram's "external systems/users"
    # requirement. Optional/empty by default so designs generated before
    # this field existed keep validating unchanged.
    actors: list[Actor] = Field(default_factory=list)

    # The Azure Service Mapping Diagram's data: one entry per major
    # logical component/actor/external dependency that has a concrete
    # Azure implementation. Empty by default for the same
    # backward-compatibility reason as `actors`.
    azure_mappings: list[AzureServiceMapping] = Field(default_factory=list)

    # Azure services supporting the architecture without mapping 1:1 to
    # any single logical component (identity, networking, secrets,
    # monitoring, CI/CD, ...).
    supporting_azure_services: list[SupportingAzureService] = Field(
        default_factory=list
    )

    assumptions: list[DesignAssumption] = Field(default_factory=list)

    open_questions: list[DesignQuestion] = Field(default_factory=list)


class ArchitectureDiagrams(BaseModel):
    """The two complementary architecture diagrams required by the
    architecture-generation phase, as SVG markup - the
    ``DiagramRendererPort.generate`` return type.

    Not itself persisted as a single artifact; ``app/design/session.py``
    unpacks this into the two separately-stored SVG blobs (see
    ``ArtifactStorePort.save_design_svg``'s ``kind`` parameter).
    """

    logical_svg: str = Field(min_length=1)
    azure_mapping_svg: str = Field(min_length=1)


class ApprovalDecision(BaseModel):
    """One approve/reject decision recorded against an architecture version.

    Persisted on ``SessionRecord.approval_history`` (see
    ``app/infrastructure/session_store.py``) - an append-only log, never
    rewritten or removed, so a session's full approval history survives
    every later refinement rather than only reflecting the latest decision.
    """

    decision: str = Field(min_length=1)  # "approved" | "rejected"
    architecture_version: int
    reason: str | None = None
    decided_by: str | None = None
    decided_at: str
