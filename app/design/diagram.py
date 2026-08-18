from __future__ import annotations

import base64
import re
from contextlib import AbstractContextManager
from pathlib import Path
from typing import NamedTuple, Protocol, cast

from graphviz import Digraph

from app.application.errors import DiagramGenerationError
from app.design.icons import component_icon_path, dependency_icon_path
from app.domain.design import DesignComponent, SystemDesignArtifact


class GraphRenderer(Protocol):
    """Minimal interface required from a Graphviz graph (or subgraph)."""

    def node(
        self,
        name: str,
        label: str,
        **attrs: str,
    ) -> None:
        """Add a node to the graph."""
        ...

    def edge(
        self,
        source: str,
        target: str,
        label: str,
        **attrs: str,
    ) -> None:
        """Add an edge to the graph."""
        ...

    def attr(
        self,
        *args: str,
        **attrs: str,
    ) -> None:
        """Set a graph/node/edge default attribute."""
        ...

    def subgraph(
        self, name: str | None = None
    ) -> AbstractContextManager[GraphRenderer]:
        """Open a subgraph, e.g. to force a shared rank or (when `name`
        starts with ``"cluster"``) to render a labeled, boxed group."""
        ...

    def pipe(self, format: str) -> bytes:
        """Render the graph."""
        ...


class _DiagramNode(NamedTuple):
    """One component or external dependency to place via
    `ArchitectureDiagramGenerator._lay_out_column`, already resolved to
    its icon (see `app/design/icons.py`)."""

    node_id: str
    name: str
    tooltip: str
    icon_path: str
    # "" for a normal component caption; a color name (e.g.
    # "darkgoldenrod") to visually set an external dependency's caption
    # apart from a component's, since both now render as icon nodes with
    # no background fill to otherwise tell them apart at a glance.
    caption_color: str = ""


# Matches the `xlink:href="...png"` (or `href="...png"` on newer
# SVG/Graphviz versions) that Graphviz writes for every node's
# `image=...png` HTML-label attribute — see `_inline_local_images`.
_LOCAL_IMAGE_HREF_PATTERN = re.compile(r'((?:xlink:href|href))="([^"]+\.png)"')


class ArchitectureDiagramGenerator:
    """Generate a high-level architecture diagram as SVG.

    The concrete ``app.application.ports.DiagramRendererPort``
    implementation — satisfied structurally via its ``generate`` method,
    no inheritance required. See that port's docstring for why this
    doesn't go through ``app.infrastructure.composition`` the way the
    agent adapters do.

    Components are grouped into one Graphviz *cluster* per
    ``DesignComponent.domain`` (see ``app/domain/design.py``), so
    related components stay visually together and most real edges stay
    short instead of arcing across the whole diagram. This replaced an
    earlier design that forced every component into one flat page-wide
    grid — see git history / the "Image Input Classification" README
    section's neighbor for why: on any design with more than a handful
    of components and interfaces, that flat grid produced a "hairball"
    of long, crossing edge splines, because every real edge was drawn
    with ``constraint="false"`` (so it couldn't influence node
    placement) between nodes whose position was decided purely by the
    grid, not by which nodes were actually related.

    Every component and external dependency renders as a small icon
    (see ``app/design/icons.py`` for how an icon is chosen) above its
    "{id}\\n{name}" caption, in the style of a typical cloud
    architecture reference diagram, rather than a plain colored box.
    """

    # Past this many total real edges (interfaces + dependency "used by"
    # edges combined), rendering every single one's name as inline label
    # text turns into unreadable clutter — dozens of small text strings
    # scattered across the diagram. Full detail is still available via
    # each edge's `tooltip` (shown on hover, and already relied on by
    # the frontend's DiagramViewer), so above this threshold inline
    # labels are dropped entirely rather than made illegibly small.
    MAX_LABELED_EDGES = 24

    # Domain shown for a component whose `domain` field is blank —
    # keeps older/unclassified designs (and anything that constructs a
    # `DesignComponent` without a domain) rendering as a single grouped
    # cluster instead of erroring or silently omitting the field.
    DEFAULT_DOMAIN = "Other Components"

    # Side length, in points, of a node's icon image within its
    # HTML-like label — see `_node_label`.
    ICON_SIZE_PX = 56

    # Caption color for an external dependency node, set apart from a
    # component's default (unset -> black) caption color.
    DEPENDENCY_CAPTION_COLOR = "darkgoldenrod"

    def _create_graph(self) -> GraphRenderer:
        graph = Digraph(
            name="system_architecture",
            format="svg",
        )

        # No fixed page size or `ratio="compress"` here: forcing a
        # multi-domain, many-edge diagram into one Letter page squeezes
        # an already-complex layout into a small bounding box, which
        # stretches and bends edges into long arcs. The frontend's
        # DiagramViewer already supports zoom/pan, so letting Graphviz
        # size the SVG naturally — as large as the actual content needs
        # — produces straighter, more readable edges at the cost of not
        # fitting on one printed page unscaled.
        #
        # `rankdir="LR"` (left-to-right) rather than top-to-bottom,
        # matching the flow direction of a typical reference cloud
        # architecture diagram (client -> gateway -> services -> data
        # stores). `nodesep`/`ranksep` are larger than plain-box-node
        # defaults would need, to leave room for each edge's `xlabel`
        # (see `_add_interfaces`) to sit clear of the icon-and-caption
        # nodes on either side of it.
        graph.attr(
            rankdir="LR",
            bgcolor="white",
            pad="0.25",
            nodesep="0.5",
            ranksep="0.9",
            # Right-angle, straight-segment edge routing instead of
            # Graphviz's default curved splines — reads as far less
            # "haphazard" for a boxes-and-arrows architecture diagram,
            # and was stress-tested at the same scales as the clustering
            # change above (up to 200 components / 300 interfaces)
            # without reproducing the `dot` crash discussed on
            # `_lay_out_column`. Edge label text moves to `xlabel`
            # instead of `label` to match — `dot` warns that plain
            # `label` isn't positioned correctly on orthogonal edges.
            splines="ortho",
        )

        # `shape="none"` — every node supplies its own HTML-like label
        # (see `_node_label`), which lays out the icon and caption
        # itself; a `box`/`filled` default here would just draw an
        # unused outline behind it.
        graph.attr(
            "node",
            shape="none",
            fontname="Helvetica",
            fontsize="11",
        )

        graph.attr(
            "edge",
            color="gray40",
            fontname="Helvetica",
            fontsize="9",
            arrowsize="0.7",
        )

        return cast(GraphRenderer, graph)

    def generate(
        self,
        design: SystemDesignArtifact,
    ) -> str:
        """Generate an SVG architecture diagram."""

        graph = self._create_graph()

        try:
            domain_of = self._add_components(graph, design)
            self._add_external_dependencies(graph, design)

            total_edges = len(design.interfaces) + sum(
                len(dependency.used_by_components)
                for dependency in design.external_dependencies
            )
            suppress_labels = total_edges > self.MAX_LABELED_EDGES

            self._add_interfaces(graph, design, domain_of, suppress_labels)
            self._add_dependency_edges(graph, design, suppress_labels)

            svg_bytes = graph.pipe(format="svg")
            svg = svg_bytes.decode("utf-8")

            return self._inline_local_images(svg)

        except Exception as exc:
            raise DiagramGenerationError(
                "Architecture diagram generation failed."
            ) from exc

    @staticmethod
    def _inline_local_images(svg: str) -> str:
        """Replace every local-filesystem PNG `href`/`xlink:href` that
        Graphviz wrote for a node's icon with an inline base64 `data:`
        URI.

        Graphviz's SVG output references an icon by the exact filesystem
        path passed to its `IMG SRC=...` HTML-label attribute — fine for
        a `dot`-produced file sitting next to that path, but this SVG is
        persisted as a Blob artifact and later rendered directly in a
        browser (`DiagramViewer.tsx`), which has no access to this
        server's filesystem. Inlining the icon bytes keeps the SVG fully
        self-contained wherever it ends up, exactly like a component's
        `image=` icon reference is meant to look regardless of where the
        SVG is opened.
        """

        def _inline(match: re.Match[str]) -> str:
            attribute, path = match.group(1), match.group(2)
            encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
            return f'{attribute}="data:image/png;base64,{encoded}"'

        return _LOCAL_IMAGE_HREF_PATTERN.sub(_inline, svg)

    @staticmethod
    def _escape_html(text: str) -> str:
        """Escape the handful of characters that are structurally
        significant inside a Graphviz HTML-like label — see
        `_node_label`. Component/dependency names and ids are free text
        (LLM- or user-supplied), so an unescaped `<`, `>`, or `&` would
        otherwise corrupt the label's HTML structure."""

        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @staticmethod
    def _node_label(node: _DiagramNode) -> str:
        """Build the HTML-like label Graphviz needs to place `node`'s
        icon above its "{id}\\n{name}" caption without the two
        overlapping.

        A plain `image=...` + `label=...` pair on a `shape="none"` node
        does NOT reserve separate space for the label under the
        installed Graphviz build (2.43.0): the label text renders
        overlapping the image's own area instead of below it, regardless
        of `labelloc`. An HTML-like label with the image and caption in
        stacked table rows lays out exactly as expected — confirmed
        visually against the alternative before choosing this approach.
        """

        size = ArchitectureDiagramGenerator.ICON_SIZE_PX
        node_id = ArchitectureDiagramGenerator._escape_html(node.node_id)
        name = ArchitectureDiagramGenerator._escape_html(node.name)

        caption = f"{node_id}<BR/>{name}"
        if node.caption_color:
            caption = f'<FONT COLOR="{node.caption_color}">{caption}</FONT>'

        return (
            '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="2">'
            f'<TR><TD FIXEDSIZE="TRUE" WIDTH="{size}" HEIGHT="{size}">'
            f'<IMG SRC="{node.icon_path}" SCALE="TRUE"/></TD></TR>'
            f"<TR><TD>{caption}</TD></TR>"
            "</TABLE>>"
        )

    @staticmethod
    def _lay_out_column(
        graph: GraphRenderer,
        nodes: list[_DiagramNode],
    ) -> None:
        """Place `nodes` into `graph` (a cluster subgraph) as a single
        top-to-bottom column, in `nodes`' order.

        Consecutive nodes are chained with an invisible, unlabeled,
        heavily-weighted edge — a normal *directed* edge, contributing a
        real (if fake) rank-ordering constraint, NOT a `rank=same`
        ("flat"/same-rank) edge. That distinction matters a lot here: an
        earlier version of this method instead wrapped items into a grid
        using nested `rank=same` subgraphs (to bound a domain's width
        instead of letting it grow as one tall column), one per row,
        inside the domain's `cluster_*`-named subgraph. That combination —
        `rank=same` nested inside a Graphviz cluster, on a graph with
        enough real edges crossing between clusters — reliably crashes the
        installed Graphviz `dot` build (2.43.0) with
        `class2.c:148: merge_chain: Assertion 'ED_to_virt(e) == NULL'
        failed`, confirmed via local reproduction at roughly 40+
        components / 60+ interfaces spread across several domains — well
        within what a real generated architecture can reach. Directed
        (non-flat) invisible edges inside a cluster, at the same or
        greater scale, do not trigger it — including with `rankdir="LR"`
        (this now lays out left-to-right, not top-to-bottom; re-verified
        against the same stress scale after that change).

        The column layout this settles on isn't just the safe fallback,
        though — it's also a closer match to how domains are drawn in a
        typical reference architecture diagram (a labeled section
        containing a stack of its components) than the wrapped grid was,
        so nothing about the visual result is a downgrade for it.
        """

        previous_id: str | None = None

        for node in nodes:
            graph.node(
                node.node_id,
                label=ArchitectureDiagramGenerator._node_label(node),
                tooltip=node.tooltip,
            )

            if previous_id is not None:
                graph.edge(
                    previous_id, node.node_id, label="", style="invis", weight="4"
                )

            previous_id = node.node_id

    @staticmethod
    def _domain_of(component: DesignComponent) -> str:
        return component.domain.strip() or ArchitectureDiagramGenerator.DEFAULT_DOMAIN

    @staticmethod
    def _group_by_domain(
        components: list[DesignComponent],
    ) -> dict[str, list[DesignComponent]]:
        """Bucket `components` by domain, preserving each domain's first
        appearance order (Python dicts preserve insertion order) — so
        clusters render in roughly the order the design introduced them,
        rather than an arbitrary or alphabetical order."""

        grouped: dict[str, list[DesignComponent]] = {}

        for component in components:
            grouped.setdefault(
                ArchitectureDiagramGenerator._domain_of(component), []
            ).append(component)

        return grouped

    @staticmethod
    def _add_components(
        graph: GraphRenderer,
        design: SystemDesignArtifact,
    ) -> dict[str, str]:
        # Caption text is deliberately just "{id}\n{name}" (e.g.
        # "C-001\nUser Interaction Component") — the full responsibility
        # stays out of it (it's already in the Requirements/Architecture
        # text panel in the UI) and is attached as a `tooltip`, which
        # Graphviz renders as an `xlink:title` on the node's link
        # element, shown on hover, without touching the node's own
        # `<title>` (still just the component id — the frontend's
        # click-to-inspect in DiagramViewer.tsx depends on that staying
        # exactly the id).
        #
        # Returns component id -> domain, so `_add_interfaces` can tell
        # whether an interface stays within one domain (and can safely
        # be allowed to influence layout) or crosses domains.
        domain_of: dict[str, str] = {}

        grouped = ArchitectureDiagramGenerator._group_by_domain(design.components)

        for index, (domain, components) in enumerate(grouped.items()):
            nodes = [
                _DiagramNode(
                    node_id=component.id,
                    name=component.name,
                    tooltip=component.responsibility,
                    icon_path=component_icon_path(
                        component.name, component.responsibility
                    ),
                )
                for component in components
            ]

            for component in components:
                domain_of[component.id] = domain

            with graph.subgraph(name=f"cluster_domain_{index}") as cluster:
                cluster.attr(
                    label=domain,
                    # Dashed, Azure-blue boundary — the same visual
                    # convention a typical Azure reference architecture
                    # diagram uses for a virtual network or other logical
                    # boundary grouping a set of resources.
                    style="dashed",
                    color="#0078D4",
                    fontname="Helvetica-Bold",
                    fontsize="12",
                    bgcolor="white",
                )
                ArchitectureDiagramGenerator._lay_out_column(cluster, nodes)

        return domain_of

    @staticmethod
    def _add_external_dependencies(
        graph: GraphRenderer,
        design: SystemDesignArtifact,
    ) -> None:
        if not design.external_dependencies:
            return

        nodes = [
            _DiagramNode(
                node_id=dependency.id,
                name=dependency.name,
                tooltip=dependency.purpose,
                icon_path=dependency_icon_path(dependency.name, dependency.purpose),
                caption_color=ArchitectureDiagramGenerator.DEPENDENCY_CAPTION_COLOR,
            )
            for dependency in design.external_dependencies
        ]

        # Dependencies aren't grouped per-domain — a single dependency is
        # often used by components across several domains (see
        # `used_by_components`), so it has no one natural "home" domain.
        # They still get their own cluster, both to visually set them
        # apart from the components above and to reuse the same column
        # layout as domain clusters.
        with graph.subgraph(name="cluster_external_dependencies") as cluster:
            cluster.attr(
                label="External Dependencies",
                style="dashed",
                color="darkgoldenrod",
                fontname="Helvetica-Bold",
                fontsize="12",
                bgcolor="white",
            )
            ArchitectureDiagramGenerator._lay_out_column(cluster, nodes)

    @staticmethod
    def _add_interfaces(
        graph: GraphRenderer,
        design: SystemDesignArtifact,
        domain_of: dict[str, str],
        suppress_labels: bool,
    ) -> None:
        for interface in design.interfaces:
            same_domain = domain_of.get(interface.source_component) == domain_of.get(
                interface.target_component
            )

            ArchitectureDiagramGenerator._add_labeled_edge(
                graph,
                source=interface.source_component,
                target=interface.target_component,
                label_id=f"__label__{interface.id}",
                label_text="" if suppress_labels else interface.name,
                tooltip=interface.purpose,
                # An interface within a single domain cluster is allowed
                # to influence layout (helping Graphviz order/route it
                # sensibly among that domain's own nodes). One that
                # crosses domains keeps `constraint="false"`, the same as
                # before: letting a cross-domain edge pull on rank
                # assignment would fight the clusters themselves, likely
                # dragging nodes toward a neighboring domain's rank
                # instead of just being drawn as a (possibly long) arrow
                # between two independently-laid-out groups.
                constraint="true" if same_domain else "false",
            )

    @staticmethod
    def _add_dependency_edges(
        graph: GraphRenderer,
        design: SystemDesignArtifact,
        suppress_labels: bool,
    ) -> None:
        for dependency in design.external_dependencies:
            for position, component_id in enumerate(dependency.used_by_components):
                # Only the first edge into a given dependency shows its
                # name as an inline label; a dependency used by several
                # components would otherwise repeat the exact same label
                # text on every incoming edge, cluttering the area around
                # that dependency's node for no added information. Every
                # edge still carries the full `tooltip` regardless.
                show_label = not suppress_labels and position == 0

                ArchitectureDiagramGenerator._add_labeled_edge(
                    graph,
                    source=component_id,
                    target=dependency.id,
                    label_id=f"__label__{dependency.id}__{component_id}",
                    label_text=dependency.name if show_label else "",
                    tooltip=dependency.purpose,
                    style="dashed",
                    color="darkgoldenrod",
                    # Dependencies aren't clustered per-domain (see
                    # `_add_external_dependencies`), so letting these
                    # edges influence rank assignment would pull a
                    # dependency's rank toward whichever component
                    # happened to be laid out last among potentially
                    # several unrelated domains — kept `False`, as before.
                    constraint="false",
                )

    @staticmethod
    def _add_labeled_edge(
        graph: GraphRenderer,
        *,
        source: str,
        target: str,
        label_id: str,
        label_text: str,
        tooltip: str,
        constraint: str,
        style: str = "solid",
        color: str = "gray40",
    ) -> None:
        """Draw a single directed connection from ``source`` to
        ``target``, optionally with a name shown along the way.

        An earlier version of this attached the name as an edge
        `xlabel` — Graphviz's own auto-placed "exterior label", positioned
        near the edge without reserving any layout space for it. That
        produced two real, user-reported defects on non-trivial diagrams:
        an xlabel rendering directly on top of a neighboring node's
        caption text, and a separate xlabel rendered visibly disconnected
        from the edge it named. Graphviz's `forcelabels="false"` escape
        hatch (drop a label instead of overlapping) was tried and
        rejected: with `rankdir="LR"` (required for this diagram's
        left-to-right flow — see `_create_graph`), the installed
        `dot` (Graphviz 2.42/2.43) drops *every* exterior label, even in
        a trivial two-node, one-edge diagram with the entire canvas
        empty — a real layout-engine limitation, not a spacing problem
        (confirmed empirically: increasing `nodesep`/`ranksep` had no
        effect).

        Instead, when there's a name to show, the single edge is split
        into two: `source -> label node -> target`, where the label node
        is a borderless, fill-less `shape="plaintext"` node whose only
        content is the name. Splitting the edge like this means the
        label is a first-class node in Graphviz's own layout — `dot`
        reserves real rank/column space for it and guarantees no other
        node overlaps it, exactly the same overlap-avoidance every
        component/dependency icon node already gets — while still
        visibly sitting *on* the connecting line (it has a real inbound
        and outbound edge segment), which reads unambiguously as "this
        interface's name" rather than a floating annotation. `tooltip`
        is set on the label node and both edge segments so hovering
        either the label or the line shows the full description
        regardless of which part the pointer happens to be over.

        When there's no name to show (label text is blank — either this
        specific edge never had one, or `_create_graph`'s caller
        suppressed all inline labels past `MAX_LABELED_EDGES`), this
        draws a single plain edge exactly as before, unchanged.
        """

        if not label_text:
            graph.edge(
                source,
                target,
                label="",
                tooltip=tooltip,
                style=style,
                color=color,
                constraint=constraint,
            )
            return

        graph.node(
            label_id,
            label_text,
            shape="plaintext",
            fontname="Helvetica",
            fontsize="9",
            fontcolor=color,
            margin="0.02,0.02",
            tooltip=tooltip,
        )

        graph.edge(
            source,
            label_id,
            label="",
            tooltip=tooltip,
            style=style,
            color=color,
            arrowhead="none",
            constraint=constraint,
        )
        graph.edge(
            label_id,
            target,
            label="",
            tooltip=tooltip,
            style=style,
            color=color,
            constraint=constraint,
        )
