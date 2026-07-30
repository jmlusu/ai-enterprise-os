"""Graph visualization module for AI Enterprise OS Graph Engine."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import networkx as nx

from ai_company.graph.export import GraphExporter


class GraphVisualizer:
    """High-level visualizer that can work with any graph engine.

    The visualizer wraps :class:`GraphExporter` and provides
    publication-quality rendering with sensible defaults for every
    graph type in the engine (organization, workflow, dependency,
    project).
    """

    def __init__(self) -> None:
        self.exporter = GraphExporter()
        self.logger = logging.getLogger(self.__class__.__name__)

    # ------------------------------------------------------------------
    #  Single-format rendering
    # ------------------------------------------------------------------

    def render(
        self,
        graph: nx.Graph,
        output_path: str,
        format: str = "auto",
        *,
        layout: str = "auto",
        figsize: tuple[float, float] = (14, 10),
        dpi: int = 200,
        node_size: int | None = None,
        node_color: str | None = None,
        edge_labels_enabled: bool = True,
        legend_enabled: bool = True,
        title: str = "",
        font_family: str = "sans-serif",
    ) -> str:
        """Render a graph to a single image file with professional styling.

        When *format* is ``'auto'`` (the default), the format is inferred
        from the *output_path* file extension (``.png`` → png, ``.svg`` → svg,
        ``.pdf`` → pdf).  Explicitly pass a format value to override.

        Args:
            graph: NetworkX graph to render.
            output_path: Destination file path.
            format: Image format (``'auto'``, ``'png'``, ``'svg'``, ``'pdf'``).

        Keyword-only arguments — see :meth:`GraphExporter.visualize` for
        full documentation of each parameter.

        Returns:
            Absolute path to the rendered file, or empty string on failure.
        """
        resolved_format = format
        if resolved_format == "auto":
            ext = Path(output_path).suffix.lstrip(".").lower()
            if ext in ("png", "svg", "pdf"):
                resolved_format = ext
            else:
                resolved_format = "png"

        return self.exporter.visualize(
            graph,
            output_path,
            resolved_format,
            layout=layout,
            figsize=figsize,
            dpi=dpi,
            node_size=node_size,
            node_color=node_color,
            edge_labels_enabled=edge_labels_enabled,
            legend_enabled=legend_enabled,
            title=title,
            font_family=font_family,
        )

    # ------------------------------------------------------------------
    #  Smart rendering (auto-detects best layout for the graph type)
    # ------------------------------------------------------------------

    def render_organization(
        self,
        graph: nx.Graph,
        output_path: str,
        format: str = "auto",
        *,
        dpi: int = 200,
        title: str = "Organization Hierarchy",
    ) -> str:
        """Render an organization chart with a top-down hierarchy layout.

        Args:
            graph: NetworkX graph to render.
            output_path: Destination file path (extension auto-detects format).
            format: Image format (``'auto'``, ``'png'``, ``'svg'``, ``'pdf'``).
            dpi: Output resolution.
            title: Figure title.
        """
        return self.render(
            graph,
            output_path,
            format,
            layout="hierarchical",
            figsize=(16, 12),
            dpi=dpi,
            title=title or "Organization Hierarchy",
        )

    def render_workflow(
        self,
        graph: nx.Graph,
        output_path: str,
        format: str = "auto",
        *,
        dpi: int = 200,
        title: str = "Workflow Graph",
    ) -> str:
        """Render a workflow graph with a left-to-right hierarchical layout.

        Args:
            graph: NetworkX graph to render.
            output_path: Destination file path (extension auto-detects format).
            format: Image format (``'auto'``, ``'png'``, ``'svg'``, ``'pdf'``).
            dpi: Output resolution.
            title: Figure title.
        """
        return self.render(
            graph,
            output_path,
            format,
            layout="hierarchical",
            figsize=(18, 8),
            dpi=dpi,
            title=title or "Workflow Graph",
        )

    def render_dependency(
        self,
        graph: nx.Graph,
        output_path: str,
        format: str = "auto",
        *,
        dpi: int = 200,
        title: str = "Dependency Graph",
    ) -> str:
        """Render a dependency graph using a spring layout.

        Args:
            graph: NetworkX graph to render.
            output_path: Destination file path (extension auto-detects format).
            format: Image format (``'auto'``, ``'png'``, ``'svg'``, ``'pdf'``).
            dpi: Output resolution.
            title: Figure title.
        """
        return self.render(
            graph,
            output_path,
            format,
            layout="spring",
            figsize=(14, 10),
            dpi=dpi,
            title=title or "Dependency Graph",
        )

    def render_projects(
        self,
        graph: nx.Graph,
        output_path: str,
        format: str = "auto",
        *,
        dpi: int = 200,
        title: str = "Project Relationships",
    ) -> str:
        """Render a project relationship graph using a circular layout.

        Args:
            graph: NetworkX graph to render.
            output_path: Destination file path (extension auto-detects format).
            format: Image format (``'auto'``, ``'png'``, ``'svg'``, ``'pdf'``).
            dpi: Output resolution.
            title: Figure title.
        """
        return self.render(
            graph,
            output_path,
            format,
            layout="circular",
            figsize=(12, 12),
            dpi=dpi,
            title=title or "Project Relationships",
        )

    # ------------------------------------------------------------------
    #  Batch export
    # ------------------------------------------------------------------

    def export_all_formats(
        self,
        graph: nx.Graph,
        base_path: str,
        formats: list[str] | None = None,
    ) -> dict[str, str]:
        """Export graph to multiple text/data formats (no images).

        Args:
            graph: NetworkX graph
            base_path: Base path for output files (without extension)
            formats: List of formats (default: json, yaml, graphml, dot)

        Returns:
            Dictionary mapping format to file path
        """
        formats = formats or ["json", "yaml", "graphml", "dot"]
        results: dict[str, str] = {}

        for fmt in formats:
            try:
                path = self.exporter.save(graph, f"{base_path}.{fmt}", fmt)
                results[fmt] = path
            except Exception as e:
                self.logger.warning(f"Failed to export {fmt}: {e}")

        return results

    def export_images(
        self,
        graph: nx.Graph,
        base_path: str,
        formats: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, str]:
        """Render the same graph to multiple image formats.

        Args:
            graph: NetworkX graph
            base_path: Base path (without extension)
            formats: Image formats (default: png, svg, pdf)
            **kwargs: Passed through to :meth:`render`.

        Returns:
            Dictionary mapping format to file path
        """
        formats = formats or ["png", "svg", "pdf"]
        results: dict[str, str] = {}
        for fmt in formats:
            try:
                path = self.render(graph, f"{base_path}.{fmt}", fmt, **kwargs)
                results[fmt] = path
            except Exception as e:
                self.logger.warning(f"Failed to export {fmt}: {e}")
        return results

    # ------------------------------------------------------------------
    #  Report
    # ------------------------------------------------------------------

    def generate_report(self, graph: nx.Graph, title: str = "Graph Report") -> str:
        """Generate a text report of graph information."""
        lines = [
            f"= {title} =",
            f"Nodes: {graph.number_of_nodes()}",
            f"Edges: {graph.number_of_edges()}",
            f"Directed: {isinstance(graph, nx.DiGraph)}",
            "",
        ]

        # Node type breakdown
        node_types: dict[str, int] = {}
        for _, data in graph.nodes(data=True):
            ntype = data.get("type", "unknown")
            node_types[ntype] = node_types.get(ntype, 0) + 1

        if node_types:
            lines.append("Node Types:")
            for ntype, count in sorted(node_types.items()):
                lines.append(f"  {ntype}: {count}")
            lines.append("")

        # Node list
        lines.append("Nodes:")
        for node, data in graph.nodes(data=True):
            label = data.get("name", data.get("label", str(node)))
            ntype = data.get("type", "")
            lines.append(f"  {node} [{ntype}] - {label}")

        return "\n".join(lines)
