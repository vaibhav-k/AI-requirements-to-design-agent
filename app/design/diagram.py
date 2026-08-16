from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol, cast

from graphviz import Digraph

from app.design.models import SystemDesignArtifact


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

    def subgraph(self) -> AbstractContextManager[GraphRenderer]:
        """Open an anonymous subgraph, e.g. to force a shared rank."""
        ...

    def pipe(self, format: str) -> bytes:
        """Render the graph."""
        ...


class DiagramGenerationError(RuntimeError):
    """Raised when diagram generation fails."""


class ArchitectureDiagramGenerator:
    """Generate a high-level architecture diagram as SVG."""

    # How many node boxes to place per row before wrapping to the next
    # row — chosen so this many compact "{id}\n{name}" boxes fit across a
    # portrait Letter page's usable width (~7.5in) without needing
    # horizontal scrolling. See `_lay_out_rows` for why this has to be a
    # manual grid rather than just picking a `rankdir`: a plain topological
    # layout puts one node per rank along the flow direction, so a design
    # with many components still produces one long row (just rotated to
    # vertical instead of horizontal) no matter which direction is chosen.
    NODES_PER_ROW = 3

    def _create_graph(self) -> GraphRenderer:
        graph = Digraph(
            name="system_architecture",
            format="svg",
        )

        # Sized to a US Letter page in portrait (8.5 x 11in) with a small
        # margin reserved outside the `size` box for print bleed.
        # `rankdir="TB"` reads top-to-bottom within the manual row grid
        # `_lay_out_rows` builds — the grid, not this attribute alone, is
        # what keeps the diagram on one page; see its docstring.
        graph.attr(
            rankdir="TB",
            bgcolor="white",
            size="7.5,10",
            ratio="compress",
            pad="0.25",
            nodesep="0.35",
            ranksep="0.4",
        )

        # Compact node style: small font, tight margins, and no fixed
        # minimum box size (Graphviz's own defaults reserve 0.75in x 0.5in
        # per node even for short labels) — labels are just "{id}\n{name}"
        # (see _add_components), so the box only needs to be as wide as
        # that, not as wide as a full responsibility sentence.
        graph.attr(
            "node",
            shape="box",
            style="rounded,filled",
            fillcolor="lightblue",
            color="steelblue",
            fontname="Helvetica",
            fontsize="11",
            margin="0.12,0.08",
            width="0",
            height="0",
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
            anchor = self._add_components(graph, design)
            self._add_external_dependencies(graph, design, anchor)
            self._add_interfaces(graph, design)
            self._add_dependency_edges(graph, design)

            svg_bytes = graph.pipe(format="svg")

            return svg_bytes.decode("utf-8")

        except Exception as exc:
            raise DiagramGenerationError(
                "Architecture diagram generation failed."
            ) from exc

    @staticmethod
    def _lay_out_rows(
        graph: GraphRenderer,
        items: list[tuple[str, str, str]],
        node_attrs: dict[str, str],
        previous_anchor: str | None,
    ) -> str | None:
        """Place `items` (id, label, tooltip) into rows of `NODES_PER_ROW`.

        Each row is pinned to a single Graphviz rank (`rank=same`), so it
        renders as one horizontal band, regardless of what the real
        interface/dependency edges added elsewhere would otherwise imply
        about layout. The rows are then chained top-to-bottom with
        invisible, non-labeled edges — one per row transition, which is
        enough to force the whole shared rank below it, since every node
        in a row already shares that one rank.

        This is what actually keeps the diagram to a fixed page width no
        matter how many components/dependencies exist: a plain topological
        layout assigns one rank per node along a dependency chain, so a
        20-component design produces 20 ranks in a single row/column
        either way — wide if `rankdir="LR"`, tall if `"TB"`, but always
        one node deep. Wrapping into a grid trades that unbounded single
        dimension for a fixed width and a height that grows with the
        component count instead.

        Returns the id of the last row's anchor node (for the next call to
        chain from), or `previous_anchor` unchanged if `items` is empty.
        """

        anchor = previous_anchor
        per_row = ArchitectureDiagramGenerator.NODES_PER_ROW

        for row_start in range(0, len(items), per_row):
            row = items[row_start : row_start + per_row]

            with graph.subgraph() as row_graph:
                row_graph.attr(rank="same")

                for node_id, label, tooltip in row:
                    row_graph.node(node_id, label=label, tooltip=tooltip, **node_attrs)

                # Pin left-to-right order within the row to match `items`'
                # order — without this, Graphviz's crossing-minimization is
                # free to reorder same-rank nodes however reduces edge
                # crossings, which reads as scrambled (row IDs out of
                # sequence) once real interface/dependency edges are added.
                row_pairs = zip(row, row[1:], strict=False)
                for (left_id, _, _), (right_id, _, _) in row_pairs:
                    row_graph.edge(left_id, right_id, label="", style="invis")

            row_anchor = row[0][0]

            if anchor is not None:
                # Layout-only — forces `anchor`'s whole rank above this
                # row's rank. Not a real relationship, so it's invisible
                # and weighted heavily to avoid stretching the rows apart.
                graph.edge(
                    anchor,
                    row_anchor,
                    label="",
                    style="invis",
                    weight="4",
                )

            anchor = row_anchor

        return anchor

    @staticmethod
    def _add_components(
        graph: GraphRenderer,
        design: SystemDesignArtifact,
    ) -> str | None:
        # Box text is deliberately just "{id}\n{name}" (e.g.
        # "C-001\nUser Interaction Component") — the full responsibility
        # stays out of the box (it's already in the Requirements/
        # Architecture text panel in the UI) and is attached as a
        # `tooltip`, which Graphviz renders as an `xlink:title` on the
        # node's link element, shown on hover, without touching the
        # node's own `<title>` (still just the component id — the
        # frontend's click-to-inspect in DiagramViewer.tsx depends on
        # that staying exactly the id).
        items = [
            (
                component.id,
                f"{component.id}\n{component.name}",
                component.responsibility,
            )
            for component in design.components
        ]

        return ArchitectureDiagramGenerator._lay_out_rows(graph, items, {}, None)

    @staticmethod
    def _add_external_dependencies(
        graph: GraphRenderer,
        design: SystemDesignArtifact,
        previous_anchor: str | None,
    ) -> str | None:
        items = [
            (dependency.id, f"{dependency.id}\n{dependency.name}", dependency.purpose)
            for dependency in design.external_dependencies
        ]

        return ArchitectureDiagramGenerator._lay_out_rows(
            graph,
            items,
            {
                "style": "rounded,dashed,filled",
                "fillcolor": "lightyellow",
                "color": "darkgoldenrod",
            },
            previous_anchor,
        )

    @staticmethod
    def _add_interfaces(
        graph: GraphRenderer,
        design: SystemDesignArtifact,
    ) -> None:
        for interface in design.interfaces:
            graph.edge(
                interface.source_component,
                interface.target_component,
                label=interface.name,
                tooltip=interface.purpose,
                # Interfaces describe a relationship, not a layout
                # requirement — the row grid built by `_lay_out_rows`
                # already decides rank order. Without this, an interface
                # that happens to point "backward" relative to row order
                # would fight that grid instead of just being drawn as a
                # (possibly upward-pointing) arrow across it.
                constraint="false",
            )

    @staticmethod
    def _add_dependency_edges(
        graph: GraphRenderer,
        design: SystemDesignArtifact,
    ) -> None:
        for dependency in design.external_dependencies:
            for component_id in dependency.used_by_components:
                # Dashed and dependency-colored so a used-by edge reads as
                # visually distinct from an interface edge at a glance,
                # rather than only being distinguishable by reading labels.
                graph.edge(
                    component_id,
                    dependency.id,
                    label=dependency.name,
                    tooltip=dependency.purpose,
                    style="dashed",
                    color="darkgoldenrod",
                    constraint="false",
                )
