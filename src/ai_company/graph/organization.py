"""Organization graph using NetworkX for AI Enterprise OS."""

from __future__ import annotations

import logging
from typing import Any

import networkx as nx

from ai_company.graph.export import GraphExporter


class OrganizationGraphEngine:
    """Models executive hierarchy and organization structure as a NetworkX graph.

    The organization graph represents:
    - Executive hierarchy (CEO -> CTO -> Engineers, etc.)
    - Board members and their roles
    - Department structure
    - Reporting lines
    - Team composition

    Args:
        exporter: Graph exporter for various output formats
    """

    def __init__(self, exporter: GraphExporter | None = None) -> None:
        self.graph = nx.DiGraph(name="Organization")
        self.exporter = exporter or GraphExporter()
        self.logger = logging.getLogger(self.__class__.__name__)

    def build_from_registry(self, registry: Any) -> None:
        """Build organization graph from registry data.

        Args:
            registry: CompanyRegistry instance with executives, departments, etc.
        """
        self.graph = nx.DiGraph(name="Organization")

        if not registry:
            return

        # Add executives as nodes
        for exec_ in getattr(registry, "executives", []) or []:
            attrs = {
                "type": "executive",
                "name": exec_.name or "",
                "title": exec_.title or "",
                "department": exec_.department or "",
                "status": exec_.status or "active",
            }
            self.graph.add_node(exec_.name, **attrs)

        # Add reporting lines as edges
        for exec_ in getattr(registry, "executives", []) or []:
            if exec_.reports_to and exec_.name:
                self.graph.add_edge(exec_.name, exec_.reports_to, type="reports_to")

        # Add direct reports edges
        for exec_ in getattr(registry, "executives", []) or []:
            if exec_.name and exec_.direct_reports:
                for report in exec_.direct_reports:
                    self.graph.add_edge(report, exec_.name, type="reports_to")

        # Add board members
        for member in getattr(registry, "board_members", []) or []:
            attrs = {
                "type": "board",
                "name": member.name or "",
                "role": member.role or "",
            }
            self.graph.add_node(member.name, **attrs)

        # Add departments
        depts = getattr(registry, "departments", {}) or {}
        for dept_name, dept_data in depts.items():
            attrs = {
                "type": "department",
                "name": dept_name,
                "description": getattr(dept_data, "description", "") or "",
            }
            self.graph.add_node(dept_name, **attrs)

        self.logger.info(
            f"Built organization graph: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges"
        )

    def get_hierarchy_level(self, node: str) -> int:
        """Get hierarchy level of a node (CEO=0, Directors=1, etc.)."""
        if not self.graph.has_node(node):
            return -1
        predecessors = list(self.graph.predecessors(node))
        if not predecessors:
            return 0
        return max(self.get_hierarchy_level(p) for p in predecessors) + 1

    def get_reporting_chain(self, node: str) -> list[str]:
        """Get the reporting chain from a node to the top."""
        chain = [node]
        current = node
        while True:
            predecessors = list(self.graph.predecessors(current))
            if not predecessors:
                break
            current = predecessors[0]
            chain.append(current)
        return chain

    def get_subordinates(self, node: str) -> list[str]:
        """Get all direct subordinates of a node."""
        if not self.graph.has_node(node):
            return []
        return list(self.graph.successors(node))

    def get_team_size(self, node: str) -> int:
        """Get total team size (direct + indirect subordinates)."""
        if not self.graph.has_node(node):
            return 0
        visited: set[str] = set()

        def count_subordinates(n: str) -> int:
            count = 0
            for sub in self.graph.successors(n):
                if sub not in visited:
                    visited.add(sub)
                    count += 1 + count_subordinates(sub)
            return count

        return count_subordinates(node)

    def to_json(self, indent: int = 2) -> str:
        """Export to JSON."""
        return self.exporter.to_json(self.graph, indent)

    def to_yaml(self) -> str:
        """Export to YAML."""
        return self.exporter.to_yaml(self.graph)

    def to_graphml(self) -> str:
        """Export to GraphML."""
        return self.exporter.to_graphml(self.graph)

    def to_dot(self) -> str:
        """Export to DOT format."""
        return self.exporter.to_dot(self.graph)

    def visualize(self, output_path: str, format: str = "png") -> str:
        """Render graph visualization to file."""
        return self.exporter.visualize(self.graph, output_path, format)

    def get_statistics(self) -> dict[str, Any]:
        """Get graph statistics."""
        try:
            return {
                "nodes": self.graph.number_of_nodes(),
                "edges": self.graph.number_of_edges(),
                "density": nx.density(self.graph),
                "is_dag": nx.is_directed_acyclic_graph(self.graph),
                "components": nx.number_weakly_connected_components(self.graph),
                "hierarchy_levels": max(
                    (self.get_hierarchy_level(n) for n in self.graph.nodes()), default=0
                ),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_executive_hierarchy(self) -> list[dict[str, Any]]:
        """Get hierarchical representation of executives."""
        hierarchy = []
        for node in self.graph.nodes():
            data = self.graph.nodes[node]
            if data.get("type") == "executive":
                hierarchy.append(
                    {
                        "name": node,
                        "title": data.get("title", ""),
                        "department": data.get("department", ""),
                        "level": self.get_hierarchy_level(node),
                        "subordinates": self.get_subordinates(node),
                        "team_size": self.get_team_size(node),
                    }
                )

        hierarchy.sort(key=lambda x: x["level"])
        return hierarchy
