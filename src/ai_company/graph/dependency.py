"""Dependency graph using NetworkX for AI Enterprise OS."""

from __future__ import annotations

import logging
from typing import Any

import networkx as nx

from ai_company.graph.export import GraphExporter


class DependencyGraphEngine:
    """Models task and artifact dependencies as a NetworkX graph."""

    def __init__(self, exporter: GraphExporter | None = None) -> None:
        self.graph = nx.DiGraph(name="Dependencies")
        self.exporter = exporter or GraphExporter()
        self.logger = logging.getLogger(self.__class__.__name__)

    def build_from_tasks(self, tasks: list[dict[str, Any]]) -> None:
        """Build dependency graph from task definitions."""
        self.graph = nx.DiGraph(name="Dependencies")

        for task in tasks:
            task_name = task.get(
                "name", task.get("id", f"task_{len(self.graph.nodes)}")
            )
            self.graph.add_node(task_name, **task)

            for dep in task.get("dependencies", []):
                if dep in self.graph:
                    self.graph.add_edge(dep, task_name, type="dependency")

    def add_dependency(self, from_task: str, to_task: str) -> None:
        """Add a dependency edge between tasks."""
        self.graph.add_edge(from_task, to_task, type="dependency")

    def get_dependents(self, node: str) -> list[str]:
        """Get all tasks that depend on the given node."""
        if node not in self.graph:
            return []
        return list(self.graph.successors(node))

    def get_dependencies(self, node: str) -> list[str]:
        """Get all dependencies of the given node."""
        if node not in self.graph:
            return []
        return list(self.graph.predecessors(node))

    def get_leaf_nodes(self) -> list[str]:
        """Get nodes with no dependents."""
        return [n for n in self.graph.nodes() if self.graph.out_degree(n) == 0]

    def get_root_nodes(self) -> list[str]:
        """Get nodes with no dependencies."""
        return [n for n in self.graph.nodes() if self.graph.in_degree(n) == 0]

    def has_cycles(self) -> bool:
        """Check for cycles in the dependency graph."""
        try:
            nx.find_cycle(self.graph)
            return True
        except nx.NetworkXNoCycle:
            return False

    def get_cycles(self) -> list[list[str]]:
        """Get all cycles in the dependency graph."""
        try:
            return [list(c) for c in nx.simple_cycles(self.graph)]
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
                "root_nodes": len(self.get_root_nodes()),
                "leaf_nodes": len(self.get_leaf_nodes()),
                "has_cycles": self.has_cycles(),
            }
        except Exception as e:
            return {"error": str(e)}
