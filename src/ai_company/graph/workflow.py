"""Workflow graph using NetworkX for AI Enterprise OS."""

from __future__ import annotations

import logging
from typing import Any, cast

import networkx as nx

from ai_company.graph.export import GraphExporter


class WorkflowGraphEngine:
    """Models workflow steps and transitions as a NetworkX graph."""

    def __init__(self, exporter: GraphExporter | None = None) -> None:
        self.graph = nx.DiGraph(name="Workflow")
        self.exporter = exporter or GraphExporter()
        self.logger = logging.getLogger(self.__class__.__name__)

    def build_from_steps(self, steps: list[dict[str, Any]]) -> None:
        """Build workflow graph from step definitions."""
        self.graph = nx.DiGraph(name="Workflow")

        for step in steps:
            step_name = step.get("name", f"step_{len(self.graph.nodes)}")
            self.graph.add_node(step_name, **step)

        # Add edges based on dependencies
        for step in steps:
            step_name = step.get("name", "")
            deps = step.get("dependencies", [])
            for dep in deps:
                if dep in self.graph:
                    self.graph.add_edge(dep, step_name, type="depends_on")

    def get_critical_path(self) -> list[str]:
        """Find the longest path through the workflow."""
        try:
            return cast("list[str]", nx.dag_longest_path(self.graph))
        except nx.NetworkXUnfeasible:
            self.logger.warning("Graph contains cycles, cannot compute critical path")
            return []
        except Exception:
            return []

    def get_execution_order(self) -> list[str]:
        """Get topological execution order."""
        try:
            return list(nx.topological_sort(self.graph))
        except nx.NetworkXUnfeasible:
            self.logger.warning("Graph contains cycles")
            return list(self.graph.nodes())

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
                "is_dag": nx.is_directed_acyclic_graph(self.graph),
                "critical_path_length": len(self.get_critical_path()),
            }
        except Exception as e:
            return {"error": str(e)}
