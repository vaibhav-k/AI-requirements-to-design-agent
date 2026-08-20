from src.domain.design import (
    DesignComponent,
    DesignInterface,
    ExternalDependency,
    SystemDesignArtifact,
)
from src.infrastructure.diagram import ArchitectureDiagramGenerator


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

    svg = ArchitectureDiagramGenerator().generate(design)

    assert "<svg" in svg
    assert "API" in svg
    assert "Document Service" in svg


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

    svg = ArchitectureDiagramGenerator().generate(design)

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

    svg = ArchitectureDiagramGenerator().generate(design)

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

    svg = ArchitectureDiagramGenerator().generate(design)

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

    svg = ArchitectureDiagramGenerator().generate(design)

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

    svg = ArchitectureDiagramGenerator().generate(design)

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

    svg = ArchitectureDiagramGenerator().generate(design)

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

    svg = ArchitectureDiagramGenerator().generate(design)

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

    svg = ArchitectureDiagramGenerator().generate(design)

    # The label text appears exactly once - as its own node's caption -
    # not duplicated across a node and a separate xlabel.
    assert svg.count("Fetch Data") == 1
    assert "<title>__label__i1</title>" in svg
    # Both split edges (api -&gt; label node, label node -&gt; service) are
    # present, so the label sits directly on the connecting line rather
    # than off to one side of it.
    assert "<title>api&#45;&gt;__label__i1</title>" in svg
    assert "<title>__label__i1&#45;&gt;service</title>" in svg
