from src.domain.design import (
    Actor,
    AzureServiceMapping,
    DesignComponent,
    DesignInterface,
    DiagramMetadata,
    ExternalDependency,
    SupportingAzureService,
    SystemDesignArtifact,
)
from src.infrastructure.diagram import ArchitectureDiagramGenerator

_METADATA = DiagramMetadata(title="Test Diagram")


def test_diagram_contains_components() -> None:
    design = SystemDesignArtifact(
        architecture_summary="Document platform.",
        components=[
            DesignComponent(
                id="api",
                name="API",
                responsibility="Handles requests.",
            ),
            DesignComponent(
                id="service",
                name="Document Service",
                responsibility="Processes documents.",
            ),
        ],
        interfaces=[
            DesignInterface(
                id="api-service",
                name="Document Request",
                purpose="Sends requests.",
                source_component="api",
                target_component="service",
            )
        ],
    )

    svg = ArchitectureDiagramGenerator().generate_logical(design, _METADATA)

    assert "<svg" in svg
    assert "API" in svg
    assert "Document Service" in svg


def test_diagram_generate_png_returns_png_bytes() -> None:
    """``generate_png`` - added for the technical-design ``.docx`` export
    path (python-docx cannot embed the SVG ``generate`` produces) - shares
    ``generate``'s ``_build_graph`` core, so this only needs to check the
    output format actually changed."""

    design = SystemDesignArtifact(
        architecture_summary="Document platform.",
        components=[
            DesignComponent(
                id="api",
                name="API",
                responsibility="Handles requests.",
            ),
        ],
    )

    png = ArchitectureDiagramGenerator().generate_logical_png(design, _METADATA)

    assert isinstance(png, bytes)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_diagram_contains_external_dependency() -> None:
    design = SystemDesignArtifact(
        architecture_summary="Document platform.",
        components=[
            DesignComponent(
                id="service",
                name="Document Service",
                responsibility="Processes documents.",
            )
        ],
        external_dependencies=[
            ExternalDependency(
                id="blob",
                name="Blob Storage",
                purpose="Stores documents.",
                used_by_components=["service"],
            )
        ],
    )

    svg = ArchitectureDiagramGenerator().generate_logical(design, _METADATA)

    assert "<svg" in svg
    assert "Blob Storage" in svg
    assert "Document Service" in svg


def test_diagram_groups_components_into_domain_clusters() -> None:
    """Every distinct `DesignComponent.domain` renders as its own labeled
    cluster - the fix for components scattering across the page with no
    visual grouping (see app/design/diagram.py's class docstring)."""

    design = SystemDesignArtifact(
        architecture_summary="Two-domain platform.",
        components=[
            DesignComponent(
                id="api",
                name="API",
                responsibility="Handles requests.",
                domain="Edge",
            ),
            DesignComponent(
                id="worker",
                name="Worker",
                responsibility="Processes jobs.",
                domain="Backend",
            ),
        ],
    )

    svg = ArchitectureDiagramGenerator().generate_logical(design, _METADATA)

    assert "Edge" in svg
    assert "Backend" in svg


def test_diagram_blank_domain_falls_back_to_default_cluster() -> None:
    """A component with no `domain` set (the field's default) still
    renders - grouped under the fallback domain label - rather than
    erroring or being dropped."""

    design = SystemDesignArtifact(
        architecture_summary="Unclassified platform.",
        components=[
            DesignComponent(id="a", name="A", responsibility="Does a."),
            DesignComponent(id="b", name="B", responsibility="Does b."),
        ],
    )

    svg = ArchitectureDiagramGenerator().generate_logical(design, _METADATA)

    assert ArchitectureDiagramGenerator.DEFAULT_DOMAIN in svg
    assert "A" in svg
    assert "B" in svg


def test_diagram_suppresses_inline_labels_past_threshold() -> None:
    """Above `MAX_LABELED_EDGES` total real edges, interface names are
    dropped from the rendered SVG text (they remain available via each
    edge's tooltip) instead of cluttering the diagram with dozens of
    inline labels."""

    threshold = ArchitectureDiagramGenerator.MAX_LABELED_EDGES

    components = [
        DesignComponent(id=f"c{i}", name=f"Component {i}", responsibility="x")
        for i in range((threshold + 1) * 2)
    ]
    interfaces = [
        DesignInterface(
            id=f"i{i}",
            name=f"UNIQUE_INTERFACE_LABEL_{i}",
            purpose=f"UNIQUE_INTERFACE_PURPOSE_{i}",
            source_component=components[2 * i].id,
            target_component=components[2 * i + 1].id,
        )
        for i in range(threshold + 1)
    ]
    design = SystemDesignArtifact(
        architecture_summary="Dense platform.",
        components=components,
        interfaces=interfaces,
    )

    svg = ArchitectureDiagramGenerator().generate_logical(design, _METADATA)

    assert "UNIQUE_INTERFACE_LABEL_0" not in svg
    # The purpose text still reaches the SVG via each edge's tooltip, even
    # though the inline label is suppressed.
    assert "UNIQUE_INTERFACE_PURPOSE_0" in svg


def test_diagram_keeps_inline_labels_below_threshold() -> None:
    """A small design (well under `MAX_LABELED_EDGES`) still shows
    interface names inline, unchanged from before the threshold was
    introduced."""

    design = SystemDesignArtifact(
        architecture_summary="Small platform.",
        components=[
            DesignComponent(id="a", name="A", responsibility="x"),
            DesignComponent(id="b", name="B", responsibility="y"),
        ],
        interfaces=[
            DesignInterface(
                id="i1",
                name="Fetch Data",
                purpose="p",
                source_component="a",
                target_component="b",
            )
        ],
    )

    svg = ArchitectureDiagramGenerator().generate_logical(design, _METADATA)

    assert "Fetch Data" in svg


def test_diagram_dependency_label_shown_once_per_dependency() -> None:
    """A dependency fanning out to several components gets its name
    rendered as an inline edge label only once, not repeated on every
    incoming edge - see `_add_dependency_edges`."""

    components = [
        DesignComponent(id=f"c{i}", name=f"Component {i}", responsibility="x")
        for i in range(4)
    ]
    design = SystemDesignArtifact(
        architecture_summary="Fan-in platform.",
        components=components,
        external_dependencies=[
            ExternalDependency(
                id="dep",
                name="Shared Dependency",
                purpose="p",
                used_by_components=[c.id for c in components],
            )
        ],
    )

    svg = ArchitectureDiagramGenerator().generate_logical(design, _METADATA)

    # Once in the dependency's own node box, and once (not four times) as
    # an edge label - the other three incoming edges carry the same
    # dependency's tooltip but no repeated inline label text.
    assert svg.count("Shared Dependency") == 2


def test_diagram_handles_large_multi_domain_design_without_crashing() -> None:
    """Regression test for a real Graphviz `dot` crash
    (`class2.c:148: merge_chain: Assertion 'ED_to_virt(e) == NULL'
    failed`) triggered by an earlier version of the diagram generator
    that nested `rank=same` row-grid subgraphs inside Graphviz clusters.
    That combination reliably crashed `dot` once a design had roughly
    this many components/domains/interfaces - well within what a real
    generated architecture can reach - so this design size is
    deliberately chosen to have caught that regression."""

    domains = [f"Domain {i}" for i in range(10)]
    components = [
        DesignComponent(
            id=f"c{d_index}_{i}",
            name=f"Component {d_index}.{i}",
            responsibility="x",
            domain=domain,
        )
        for d_index, domain in enumerate(domains)
        for i in range(5)
    ]
    interfaces = [
        DesignInterface(
            id=f"i{i}",
            name=f"iface{i}",
            purpose="p",
            source_component=components[i % len(components)].id,
            target_component=components[(i * 7 + 3) % len(components)].id,
        )
        for i in range(60)
        if components[i % len(components)].id
        != components[(i * 7 + 3) % len(components)].id
    ]
    design = SystemDesignArtifact(
        architecture_summary="Large platform.",
        components=components,
        interfaces=interfaces,
        external_dependencies=[
            ExternalDependency(
                id="dep",
                name="Shared Dependency",
                purpose="p",
                used_by_components=[c.id for c in components[:5]],
            )
        ],
    )

    svg = ArchitectureDiagramGenerator().generate_logical(design, _METADATA)

    assert "<svg" in svg


def test_diagram_labeled_interface_uses_a_label_node_not_an_xlabel() -> None:
    """Regression test for a real overlap bug reported against a
    generated diagram: an interface's edge label rendered directly on
    top of a neighboring node's caption text, and - separately - a
    label rendered visibly disconnected from the edge line it named.

    Both defects traced back to using Graphviz's `xlabel` (an
    auto-placed "exterior label" that reserves no layout space and can
    be positioned anywhere clear of *some* overlaps, or forced to
    overlap, or dropped - see `_add_labeled_edge`'s docstring for the
    full investigation, including why the `forcelabels="false"`
    alternative was tried and rejected). The fix routes a labeled edge
    through an intermediate borderless `shape="plaintext"` node instead,
    so Graphviz's core layout - not the exterior-label heuristic -
    reserves real space for it and guarantees no overlap, while the
    label still sits directly on the connecting line.

    This is asserted on the rendered SVG's `<title>` elements, which
    Graphviz emits one per node/edge named after its Graphviz identity
    (a node's `<title>` is its id; an edge's is `id1->id2`). A plain
    `xlabel` never produces its own node, so a `<title>` for the label
    text itself is a signal this is going through the label-node path."""

    design = SystemDesignArtifact(
        architecture_summary="Document platform.",
        components=[
            DesignComponent(id="api", name="API", responsibility="x"),
            DesignComponent(id="service", name="Service", responsibility="y"),
        ],
        interfaces=[
            DesignInterface(
                id="i1",
                name="Fetch Data",
                purpose="p",
                source_component="api",
                target_component="service",
            )
        ],
    )

    svg = ArchitectureDiagramGenerator().generate_logical(design, _METADATA)

    # The label text appears exactly once - as its own node's caption -
    # not duplicated across a node and a separate xlabel.
    assert svg.count("Fetch Data") == 1
    assert "<title>__label__i1</title>" in svg
    # Both split edges (api -&gt; label node, label node -&gt; service) are
    # present, so the label sits directly on the connecting line rather
    # than off to one side of it.
    assert "<title>api&#45;&gt;__label__i1</title>" in svg
    assert "<title>__label__i1&#45;&gt;service</title>" in svg


def test_azure_mapping_diagram_shows_mapped_service_and_shares_component_id() -> None:
    """The Azure Service Mapping Diagram renders the mapped Azure service
    name AND keeps the same node id as the Logical Architecture Diagram -
    the core traceability requirement: a reviewer must be able to find a
    component's Azure implementation by its shared id."""

    design = SystemDesignArtifact(
        architecture_summary="Document platform.",
        components=[
            DesignComponent(
                id="api",
                name="API",
                responsibility="Handles requests.",
            ),
        ],
        azure_mappings=[
            AzureServiceMapping(
                id="map-api",
                component_id="api",
                azure_service="Azure App Service",
                rationale="Managed PaaS hosting.",
                connectivity="public-endpoint",
                trust_zone="Public",
            )
        ],
    )

    logical_svg = ArchitectureDiagramGenerator().generate_logical(design, _METADATA)
    azure_svg = ArchitectureDiagramGenerator().generate_azure_mapping(design, _METADATA)

    assert "<title>api</title>" in logical_svg
    assert "<title>api</title>" in azure_svg
    assert "Azure App Service" in azure_svg
    # The Logical diagram is technology-agnostic - it must never show the
    # Azure service name.
    assert "Azure App Service" not in logical_svg


def test_azure_mapping_diagram_omits_components_with_no_mapping() -> None:
    """A component with no `AzureServiceMapping` entry has nothing to
    show on this diagram, so it's omitted rather than rendered as an
    empty/placeholder Azure node."""

    design = SystemDesignArtifact(
        architecture_summary="Partially mapped platform.",
        components=[
            DesignComponent(id="api", name="API", responsibility="x"),
            DesignComponent(id="unmapped", name="Unmapped", responsibility="y"),
        ],
        azure_mappings=[
            AzureServiceMapping(
                id="map-api", component_id="api", azure_service="Azure App Service"
            )
        ],
    )

    azure_svg = ArchitectureDiagramGenerator().generate_azure_mapping(design, _METADATA)

    assert "<title>api</title>" in azure_svg
    assert "<title>unmapped</title>" not in azure_svg


def test_azure_mapping_diagram_renders_supporting_services() -> None:
    design = SystemDesignArtifact(
        architecture_summary="Platform with identity.",
        components=[
            DesignComponent(id="api", name="API", responsibility="x"),
        ],
        azure_mappings=[
            AzureServiceMapping(
                id="map-api", component_id="api", azure_service="Azure App Service"
            )
        ],
        supporting_azure_services=[
            SupportingAzureService(
                id="identity",
                azure_service="Microsoft Entra ID",
                category="Identity",
                purpose="Authenticates users.",
                applies_to_components=["api"],
            )
        ],
    )

    azure_svg = ArchitectureDiagramGenerator().generate_azure_mapping(design, _METADATA)

    assert "Microsoft Entra ID" in azure_svg
    assert "<title>identity</title>" in azure_svg
    assert "supports" in azure_svg
    # The "supports" label splits the edge into two segments through an
    # intermediate label node (see `_add_labeled_edge`) rather than a
    # single direct edge, so this checks for the first segment.
    assert "identity&#45;&gt;__support_label__identity__api" in azure_svg


def test_logical_diagram_renders_actors_and_async_edge_style() -> None:
    design = SystemDesignArtifact(
        architecture_summary="Event-driven platform.",
        components=[
            DesignComponent(id="api", name="API", responsibility="x"),
        ],
        actors=[Actor(id="user", name="End User", kind="user", description="A user.")],
        interfaces=[
            DesignInterface(
                id="i1",
                name="Order Placed",
                purpose="Notifies downstream systems.",
                source_component="user",
                target_component="api",
                flow_type="async",
            )
        ],
    )

    svg = ArchitectureDiagramGenerator().generate_logical(design, _METADATA)

    assert "<title>user</title>" in svg
    assert "Order Placed" in svg
    assert "event" in svg


def test_diagram_metadata_block_is_rendered() -> None:
    metadata = DiagramMetadata(
        title="My Diagram",
        description="A test description.",
        scope="Test scope.",
        author="TBD",
        version=3,
        last_updated="2026-01-01T00:00:00+00:00",
    )
    design = SystemDesignArtifact(
        architecture_summary="x",
        components=[DesignComponent(id="a", name="A", responsibility="x")],
    )

    svg = ArchitectureDiagramGenerator().generate_logical(design, metadata)

    assert "My Diagram" in svg
    assert "A test description." in svg
    assert "Version: 3" in svg
