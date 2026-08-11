from __future__ import annotations

from typing import Protocol, cast

from graphviz import Digraph

from app.design.models import SystemDesignArtifact


class GraphRenderer(Protocol):
    """Minimal interface required from a Graphviz graph."""

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
    ) -> None:
        """Add an edge to the graph."""
        ...

    def pipe(self, format: str) -> bytes:
        """Render the graph."""
        ...


class DiagramGenerationError(RuntimeError):
    """Raised when diagram generation fails."""


class ArchitectureDiagramGenerator:
    """Generate a high-level architecture diagram as SVG."""

    def _create_graph(self) -> GraphRenderer:
        graph = Digraph(
            name="system_architecture",
            format="svg",
        )

        graph.attr(
            rankdir="LR",
            bgcolor="white",
            pad="0.5",
            nodesep="0.6",
            ranksep="0.8",
        )

        graph.attr(
            "node",
            shape="box",
            style="rounded,filled",
            fillcolor="lightblue",
            color="steelblue",
            fontname="Arial",
        )

        graph.attr(
            "edge",
            color="gray40",
            fontname="Arial",
        )

        return cast(GraphRenderer, graph)

    def generate(
        self,
        design: SystemDesignArtifact,
    ) -> str:
        """Generate an SVG architecture diagram."""

        graph = self._create_graph()

        try:
            self._add_components(graph, design)
            self._add_external_dependencies(graph, design)
            self._add_interfaces(graph, design)
            self._add_dependency_edges(graph, design)

            svg_bytes = graph.pipe(format="svg")

            return svg_bytes.decode("utf-8")

        except Exception as exc:
            raise DiagramGenerationError(
                "Architecture diagram generation failed."
            ) from exc

    @staticmethod
    def _add_components(
        graph: GraphRenderer,
        design: SystemDesignArtifact,
    ) -> None:
        for component in design.components:
            label = f"{component.name}\n{component.responsibility}"

            graph.node(
                component.id,
                label=label,
            )

    @staticmethod
    def _add_external_dependencies(
        graph: GraphRenderer,
        design: SystemDesignArtifact,
    ) -> None:
        for dependency in design.external_dependencies:
            label = f"{dependency.name}\n{dependency.purpose}"

            graph.node(
                dependency.id,
                label=label,
                shape="box",
                style="rounded,dashed,filled",
                fillcolor="lightyellow",
                color="darkgoldenrod",
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
            )

    @staticmethod
    def _add_dependency_edges(
        graph: GraphRenderer,
        design: SystemDesignArtifact,
    ) -> None:
        for dependency in design.external_dependencies:
            for component_id in dependency.used_by_components:
                graph.edge(
                    component_id,
                    dependency.id,
                    label=dependency.name,
                )
