"""Graph export utility for AI Enterprise OS Graph Engine."""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from typing import Any, cast

import networkx as nx
import yaml

# Professionally curated color palette for node types
COLOR_PALETTE: dict[str, str] = {
    # Organization roles
    "ceo": "#8B1A1A",
    "cto": "#1A6B8B",
    "cfo": "#1A8B4A",
    "coo": "#8B6F1A",
    "executive": "#2E86AB",
    "manager": "#048A81",
    "engineer": "#C73E1D",
    "board": "#A23B72",
    "department": "#F18F01",
    # Edge / relationship types
    "reports_to": "#3498DB",
    "depends_on": "#E67E22",
    "dependency": "#E67E22",
    "related": "#2ECC71",
    # Status
    "active": "#27AE60",
    "inactive": "#95A5A6",
    "pending": "#F39C12",
    "archived": "#7F8C8D",
    # Fallback
    "default": "#6C757D",
}


class GraphExporter:
    """Exports NetworkX graphs to various formats."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    # ------------------------------------------------------------------
    #  Text-format exporters (JSON, YAML, GraphML, DOT)
    # ------------------------------------------------------------------

    def to_json(self, graph: nx.Graph, indent: int = 2) -> str:
        """Export graph to JSON."""
        data = nx.node_link_data(graph)
        return json.dumps(data, indent=indent)

    def to_yaml(self, graph: nx.Graph) -> str:
        """Export graph to YAML."""
        data = nx.node_link_data(graph)
        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    def to_graphml(self, graph: nx.Graph) -> str:
        """Export graph to GraphML."""
        output = io.StringIO()
        nx.write_graphml(graph, output)
        return output.getvalue()

    def to_dot(self, graph: nx.Graph) -> str:
        """Export graph to DOT format."""
        output = io.StringIO()

        if isinstance(graph, nx.DiGraph):
            output.write("digraph G {\n")
        else:
            output.write("graph G {\n")

        # Write nodes
        for node, data in graph.nodes(data=True):
            label = data.get("name", data.get("label", str(node)))
            node_type = data.get("type", "node")
            output.write(f'    "{node}" [label="{label}", type="{node_type}"];\n')

        # Write edges
        for source, target, data in graph.edges(data=True):
            edge_type = data.get("type", "edge")
            if isinstance(graph, nx.DiGraph):
                output.write(f'    "{source}" -> "{target}" [label="{edge_type}"];\n')
            else:
                output.write(f'    "{source}" -- "{target}" [label="{edge_type}"];\n')

        output.write("}\n")
        return output.getvalue()

    # ------------------------------------------------------------------
    #  Layout helpers
    # ------------------------------------------------------------------

    def _hierarchical_layout(
        self, graph: nx.DiGraph
    ) -> dict[Any, tuple[float, float]] | None:
        """Create a top-to-bottom hierarchical layout for directed acyclic graphs.

        Assigns each node a layer based on its longest-path distance from root
        nodes (sources), then distributes nodes horizontally within each layer.
        """
        if graph.number_of_nodes() == 0:
            return {}

        # Identify roots (nodes with no incoming edges)
        roots = [n for n in graph.nodes() if graph.in_degree(n) == 0]
        if not roots:
            roots = [list(graph.nodes())[0]]

        # Assign each node to a layer (longest-path distance from any root)
        layers: dict[Any, int] = {}
        for node in graph.nodes():
            max_depth = 0
            for root in roots:
                try:
                    length = nx.shortest_path_length(graph, root, node)
                    max_depth = max(max_depth, length)
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    pass
            layers[node] = max_depth

        max_layer = max(layers.values()) if layers else 0
        pos: dict[Any, tuple[float, float]] = {}
        for layer in range(max_layer + 1):
            nodes_in_layer = [n for n, v in layers.items() if v == layer]
            n_in_layer = len(nodes_in_layer)
            for i, node in enumerate(nodes_in_layer):
                x = (i - (n_in_layer - 1) / 2.0) * 2.5
                y = -layer * 3.5
                pos[node] = (float(x), float(y))
        return pos

    def _compute_layout(
        self,
        graph: nx.Graph,
        layout: str,
    ) -> dict[Any, tuple[float, float]] | None:
        """Compute node positions using the requested layout algorithm."""
        try:
            import numpy as np
        except ImportError:
            return None

        n = graph.number_of_nodes()
        if n == 0:
            return {}

        try:
            if layout == "spring":
                k = 3.0 / np.sqrt(n) if n > 1 else 1.0
                return cast(
                    "dict[Any, tuple[float, float]]",
                    nx.spring_layout(graph, k=k, iterations=100, seed=42),
                )
            elif layout == "kamada_kawai":
                return cast(
                    "dict[Any, tuple[float, float]]", nx.kamada_kawai_layout(graph)
                )
            elif layout == "circular":
                return cast("dict[Any, tuple[float, float]]", nx.circular_layout(graph))
            elif layout == "shell":
                return cast("dict[Any, tuple[float, float]]", nx.shell_layout(graph))
            elif layout == "spiral":
                return cast("dict[Any, tuple[float, float]]", nx.spiral_layout(graph))
            elif layout == "random":
                return cast(
                    "dict[Any, tuple[float, float]]", nx.random_layout(graph, seed=42)
                )
            elif layout == "hierarchical" and isinstance(graph, nx.DiGraph):
                hier = self._hierarchical_layout(graph)
                if hier is not None:
                    return hier
                # fall through to spring
                return cast(
                    "dict[Any, tuple[float, float]]", nx.spring_layout(graph, seed=42)
                )
            else:
                self.logger.warning(
                    f"Unknown layout '{layout}', falling back to spring"
                )
                return cast(
                    "dict[Any, tuple[float, float]]", nx.spring_layout(graph, seed=42)
                )
        except Exception as e:
            self.logger.warning(f"Layout '{layout}' failed: {e}")
            return None

    # ------------------------------------------------------------------
    #  Publication-quality visualisation
    # ------------------------------------------------------------------

    def visualize(
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
        """Render graph to a publication-quality image file.

        When *format* is ``'auto'`` (default), it is inferred from the
        *output_path* file extension (``.png`` → png, ``.svg`` → svg,
        ``.pdf`` → pdf).  This lets callers simply write::

            exporter.visualize(graph, "org_chart.svg")

        and get an SVG without having to pass ``format="svg"``.

        Args:
            graph: NetworkX graph to render.
            output_path: Destination file path (extension may determine
                format when *format* is ``'auto'``).
            format: Image format.  ``'auto'``, ``'png'``, ``'svg'``,
                or ``'pdf'``.

        Keyword-only arguments (all optional):
            layout: Layout algorithm. ``'auto'`` picks spring for undirected
                graphs and hierarchical for directed acyclic graphs.
                Other options: ``'spring'``, ``'kamada_kawai'``, ``'circular'``,
                ``'shell'``, ``'spiral'``, ``'random'``, ``'hierarchical'``.
            figsize: Figure dimensions (width, height) in inches.
            dpi: Output resolution (dots per inch). Higher = sharper.
            node_size: Base node radius in points. When ``None`` (default),
                sizes are scaled by degree centrality (range 500–3000).
            node_color: Override colour for all nodes (any matplotlib
                colour spec). When ``None``, colours are drawn from
                :data:`COLOR_PALETTE` based on each node's ``'type'``
                attribute.
            edge_labels_enabled: Whether to draw edge-type labels.
            legend_enabled: Whether to draw a legend mapping colours to
                node types.
            title: Optional figure title (displayed above the graph).
            font_family: Matplotlib font family name.

        Returns:
            Absolute path to the rendered file, or empty string on failure.
        """
        # ---- auto-detect format from file extension ---------------------
        resolved_format = format
        if resolved_format == "auto":
            ext = Path(output_path).suffix.lstrip(".").lower()
            if ext in ("png", "svg", "pdf"):
                resolved_format = ext
            else:
                resolved_format = "png"

        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import numpy as np
            from matplotlib.patches import Patch
        except ImportError:
            self.logger.warning("matplotlib not available, cannot render PNG/SVG/PDF")
            return ""

        n_nodes = graph.number_of_nodes()
        if n_nodes == 0:
            self.logger.warning("Empty graph — nothing to render")
            return ""

        # ---- preserve / temporarily override rcParams -------------------
        _rc = {
            k: plt.rcParams[k]
            for k in ("font.family", "font.size", "axes.facecolor", "figure.facecolor")
        }
        try:
            plt.rcParams.update(
                {
                    "font.family": font_family,
                    "font.size": 11,
                    "axes.facecolor": "#FAFAFA",
                    "figure.facecolor": "white",
                }
            )

            # ---- layout -------------------------------------------------
            actual_layout = layout
            if actual_layout == "auto":
                if isinstance(graph, nx.DiGraph) and n_nodes > 1:
                    actual_layout = "hierarchical"
                else:
                    actual_layout = "kamada_kawai" if n_nodes < 80 else "spring"

            pos = self._compute_layout(graph, actual_layout)
            if pos is None:
                # ultimate fallback
                pos = nx.spring_layout(
                    graph, k=3.0 / np.sqrt(n_nodes), iterations=100, seed=42
                )

            # ---- node colours -------------------------------------------
            color_map: list[str] = []
            type_set: set[str] = set()
            for _node, data in graph.nodes(data=True):
                ntype = str(data.get("type", "default"))
                type_set.add(ntype)
                color_map.append(COLOR_PALETTE.get(ntype, COLOR_PALETTE["default"]))

            if node_color is not None:
                color_map = [node_color] * n_nodes

            # ---- node sizes ---------------------------------------------
            if node_size is not None:
                sizes = [node_size] * n_nodes
            else:
                cent = nx.degree_centrality(graph)
                c_min = min(cent.values()) if cent else 0.0
                c_max = max(cent.values()) if cent else 1.0
                c_rng = c_max - c_min if c_max != c_min else 1.0
                sizes = [
                    int(500 + 2500.0 * (cent.get(n, 0.0) - c_min) / c_rng)
                    for n in graph.nodes()
                ]

            # ---- figure & axes ------------------------------------------
            fig, ax = plt.subplots(1, 1, figsize=figsize)
            ax.set_facecolor("#FAFAFA")

            # ---- edges (drawn first so they sit behind nodes) -----------
            nx.draw_networkx_edges(
                graph,
                pos,
                ax=ax,
                edge_color="#B0B0B0",
                arrows=isinstance(graph, nx.DiGraph),
                arrowsize=18,
                arrowstyle="-|>",
                width=1.5,
                alpha=0.7,
                connectionstyle="arc3,rad=0.1"
                if graph.number_of_edges() > 10
                else "arc3,rad=0.0",
                min_source_margin=20,
                min_target_margin=20,
            )

            # ---- nodes --------------------------------------------------
            nx.draw_networkx_nodes(
                graph,
                pos,
                ax=ax,
                node_color=color_map,
                node_size=sizes,
                edgecolors="white",
                linewidths=2.0,
                alpha=0.92,
            )

            # ---- labels -------------------------------------------------
            labels = {}
            for node, data in graph.nodes(data=True):
                labels[node] = str(data.get("name", data.get("label", node)))

            nx.draw_networkx_labels(
                graph,
                pos,
                ax=ax,
                labels=labels,
                font_size=10,
                font_weight="bold",
                font_color="#2C3E50",
            )

            # ---- edge labels --------------------------------------------
            if edge_labels_enabled:
                edge_lbls: dict[tuple[Any, Any], str] = {}
                for u, v, data in graph.edges(data=True):
                    et = str(data.get("type", data.get("label", "")))
                    if et and et not in ("edge", ""):
                        edge_lbls[(u, v)] = et
                if edge_lbls:
                    nx.draw_networkx_edge_labels(
                        graph,
                        pos,
                        ax=ax,
                        edge_labels=edge_lbls,
                        font_size=8,
                        font_color="#7F8C8D",
                        label_pos=0.5,
                        bbox=dict(
                            boxstyle="round,pad=0.15",
                            facecolor="white",
                            edgecolor="none",
                            alpha=0.75,
                        ),
                    )

            # ---- legend -------------------------------------------------
            if legend_enabled and len(type_set) > 1 and node_color is None:
                legend_elements = []
                for ntype in sorted(type_set):
                    c = COLOR_PALETTE.get(ntype, COLOR_PALETTE["default"])
                    legend_elements.append(
                        Patch(
                            facecolor=c,
                            edgecolor="white",
                            label=ntype.replace("_", " ").title(),
                        )
                    )
                ax.legend(
                    handles=legend_elements,
                    loc="upper right",
                    fontsize=10,
                    framealpha=0.9,
                    edgecolor="#D0D0D0",
                    title="Node Types",
                    title_fontsize=11,
                )

            # ---- title --------------------------------------------------
            if title:
                ax.set_title(
                    title, fontsize=16, fontweight="bold", pad=20, color="#2C3E50"
                )

            ax.axis("off")

            # ---- finalise & save ----------------------------------------
            plt.tight_layout()
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(
                str(path),
                format=resolved_format,
                dpi=dpi,
                bbox_inches="tight",
                pad_inches=0.3,
            )
            plt.close()

            self.logger.info(
                "Rendered %s → %s (%s, %ddpi, %d nodes, layout=%s)",
                graph.name if hasattr(graph, "name") and graph.name else "graph",
                path,
                resolved_format,
                dpi,
                n_nodes,
                actual_layout,
            )
            return str(path)

        except ImportError:
            self.logger.warning("matplotlib not available, cannot render PNG/SVG/PDF")
            return ""
        except Exception:
            self.logger.exception("Unexpected error during graph rendering")
            return ""
        finally:
            plt.rcParams.update(cast(Any, _rc))

    def save(self, graph: nx.Graph, output_path: str, format: str = "json") -> str:
        """Save graph to file in specified format."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if format == "json":
            content = self.to_json(graph)
        elif format == "yaml":
            content = self.to_yaml(graph)
        elif format == "graphml":
            content = self.to_graphml(graph)
        elif format == "dot":
            content = self.to_dot(graph)
        elif format in ("png", "svg", "pdf"):
            return self.visualize(graph, output_path, format)
        else:
            raise ValueError(f"Unsupported format: {format}")

        path.write_text(content, encoding="utf-8")
        return str(path)
