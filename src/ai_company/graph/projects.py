"""Project graph using NetworkX for AI Enterprise OS."""

from __future__ import annotations

import logging
from typing import Any

import networkx as nx

from ai_company.graph.export import GraphExporter


class ProjectGraphEngine:
    """Models project relationships and dependencies as a NetworkX graph."""

    def __init__(self, exporter: GraphExporter | None = None) -> None:
        self.graph = nx.Graph(name="Projects")
        self.exporter = exporter or GraphExporter()
        self.logger = logging.getLogger(self.__class__.__name__)

    def build_from_projects(self, projects: list[dict[str, Any]]) -> None:
        """Build project graph from project definitions."""
        self.graph = nx.Graph(name="Projects")

        for project in projects:
            proj_name = project.get("name", f"project_{len(self.graph.nodes)}")
            self.graph.add_node(proj_name, **project)

        # Add edges for related projects
        for project in projects:
            proj_name = project.get("name", "")
            related = project.get("related_projects", [])
            for rel in related:
                if rel in self.graph:
                    self.graph.add_edge(proj_name, rel, type="related")

    def get_project_clusters(self) -> list[list[str]]:
        """Get clusters (connected components) of projects."""
        return [list(c) for c in nx.connected_components(self.graph)]

    def get_central_projects(self, top_n: int = 5) -> list[str]:
        """Get most central projects by degree centrality."""
        centrality = nx.degree_centrality(self.graph)
        sorted_projects = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
        return [p[0] for p in sorted_projects[:top_n]]

    def to_json(self, indent: int = 2) -> str:
        return self.exporter.to_json(self.graph, indent)

    def to_yaml(self) -> str:
        return self.exporter.to_yaml(self.graph)

    def to_dot(self) -> str:
        return self.exporter.to_dot(self.graph)

    def visualize(self, output_path: str, format: str = "png") -> str:
        return self.exporter.visualize(self.graph, output_path, format)

    def get_statistics(self) -> dict[str, Any]:
        try:
            return {
                "nodes": self.graph.number_of_nodes(),
                "edges": self.graph.number_of_edges(),
                "clusters": len(self.get_project_clusters()),
                "density": nx.density(self.graph),
            }
        except Exception as e:
            return {"error": str(e)}
