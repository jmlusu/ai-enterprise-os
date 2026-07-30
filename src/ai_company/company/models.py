"""Internal data models for the organization generator.

These models represent the generated organizational structure and are
distinct from the :mod:`ai_company.models.company` Pydantic models that
represent the validated registry input.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from typing import Any


@dataclasses.dataclass(frozen=True)
class OrgNode:
    """A single node in the organization tree.

    Attributes:
        id: Unique identifier for this node (e.g. ``"exec:ceo"``).
        name: Display name of the entity.
        title: Job title or role label.
        node_type: Category — ``"board"``, ``"executive"``, ``"department"``,
            ``"role"``, ``"specialist"``.
        level: Hierarchy depth (0 = board/C-suite, 1 = direct reports, …).
        department: Department this node belongs to (if applicable).
        parent_id: ID of the parent node, or ``None`` for root nodes.
        metadata: Free-form key-value store for extensions.
    """

    id: str
    name: str
    title: str = ""
    node_type: str = "executive"
    level: int = 0
    department: str = ""
    parent_id: str | None = None
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class OrgEdge:
    """A directed relationship between two :class:`OrgNode` instances.

    Attributes:
        source_id: ID of the source node.
        target_id: ID of the target node.
        edge_type: Relationship kind — ``"reports_to"``, ``"leads"``,
            ``"member_of"``, ``"communicates_with"``, ``"depends_on"``.
        metadata: Free-form key-value store.
    """

    source_id: str
    target_id: str
    edge_type: str = "reports_to"
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class OrgMetadata:
    """Aggregate metrics about the generated organization."""

    total_nodes: int = 0
    total_edges: int = 0
    max_depth: int = 0
    node_type_counts: dict[str, int] = dataclasses.field(default_factory=dict)
    span_of_control: dict[str, int] = dataclasses.field(default_factory=dict)
    orphans: list[str] = dataclasses.field(default_factory=list)
    cycles: list[list[str]] = dataclasses.field(default_factory=list)
    warnings: list[str] = dataclasses.field(default_factory=list)


class OrgGraph:
    """Container for the complete organization graph.

    Provides convenience methods for querying nodes, edges, and
    performing integrity checks.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, OrgNode] = {}
        self._edges: list[OrgEdge] = []
        self._adjacency: dict[str, list[str]] = defaultdict(list)
        self._reverse_adj: dict[str, list[str]] = defaultdict(list)

    # ---- mutation -----------------------------------------------------------

    def add_node(self, node: OrgNode) -> None:
        """Add or replace an :class:`OrgNode`."""
        self._nodes[node.id] = node

    def add_edge(self, edge: OrgEdge) -> None:
        """Add an :class:`OrgEdge` and update adjacency indexes."""
        self._edges.append(edge)
        self._adjacency[edge.source_id].append(edge.target_id)
        self._reverse_adj[edge.target_id].append(edge.source_id)

    # ---- queries ------------------------------------------------------------

    def get_node(self, node_id: str) -> OrgNode | None:
        return self._nodes.get(node_id)

    @property
    def nodes(self) -> dict[str, OrgNode]:
        return dict(self._nodes)

    @property
    def edges(self) -> list[OrgEdge]:
        return list(self._edges)

    def children_of(self, node_id: str) -> list[OrgNode]:
        """Return direct children (nodes that report *to* node_id).

        Edges go subordinate → manager, so incoming edges (reverse_adj)
        represent a node's subordinates.
        """
        return [
            self._nodes[cid]
            for cid in self._reverse_adj.get(node_id, [])
            if cid in self._nodes
        ]

    def parents_of(self, node_id: str) -> list[OrgNode]:
        """Return direct parents (nodes that *node_id* reports to).

        Edges go subordinate → manager, so outgoing edges (adjacency)
        represent a node's managers.
        """
        return [
            self._nodes[pid]
            for pid in self._adjacency.get(node_id, [])
            if pid in self._nodes
        ]

    def nodes_by_type(self, node_type: str) -> list[OrgNode]:
        return [n for n in self._nodes.values() if n.node_type == node_type]

    def nodes_by_level(self, level: int) -> list[OrgNode]:
        return [n for n in self._nodes.values() if n.level == level]

    def subgraph(self, node_id: str) -> OrgGraph:
        """Return the sub-tree rooted at *node_id* (breadth-first)."""
        sub = OrgGraph()
        stack = [node_id]
        visited: set[str] = set()
        while stack:
            nid = stack.pop()
            if nid in visited or nid not in self._nodes:
                continue
            visited.add(nid)
            sub.add_node(self._nodes[nid])
            for edge in self._edges:
                if edge.source_id == nid:
                    sub.add_edge(edge)
                    if edge.target_id not in visited:
                        stack.append(edge.target_id)
        return sub

    # ---- integrity ----------------------------------------------------------

    def detect_cycles(self) -> list[list[str]]:
        """Return all elementary cycles using a DFS-based approach.

        Because the graph is intended to be a directed acyclic graph (DAG),
        any cycle is a data integrity error.
        """
        visited: set[str] = set()
        rec_stack: set[str] = set()
        cycles: list[list[str]] = []
        parent: dict[str, str | None] = {}

        def _dfs(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            for child_id in self._adjacency.get(node, []):
                if child_id not in self._nodes:
                    continue
                if child_id not in visited:
                    parent[child_id] = node
                    _dfs(child_id)
                elif child_id in rec_stack:
                    # reconstruct cycle
                    cycle = [child_id, node]
                    cur = node
                    while cur != child_id and parent.get(cur) is not None:
                        cur = parent[cur]  # type: ignore[assignment]
                        if cur is not None:
                            cycle.append(cur)
                    cycles.append(list(reversed(cycle)))
            rec_stack.discard(node)

        for nid in self._nodes:
            if nid not in visited:
                parent[nid] = None
                _dfs(nid)

        return cycles

    def compute_metadata(self) -> OrgMetadata:
        """Compute aggregate metadata for the current graph."""
        meta = OrgMetadata()
        meta.total_nodes = len(self._nodes)
        meta.total_edges = len(self._edges)

        type_counts: dict[str, int] = defaultdict(int)
        for n in self._nodes.values():
            type_counts[n.node_type] += 1
            meta.max_depth = max(meta.max_depth, n.level)
        meta.node_type_counts = dict(type_counts)

        # span of control: count direct children per node
        for nid in self._nodes:
            children = self.children_of(nid)
            if children:
                meta.span_of_control[nid] = len(children)

        # orphans: nodes with no parent and no children (isolated)
        for nid, node in self._nodes.items():
            has_parent = bool(self._reverse_adj.get(nid))
            has_children = bool(self._adjacency.get(nid))
            if not has_parent and not has_children and node.level > 0:
                meta.orphans.append(nid)

        meta.cycles = self.detect_cycles()
        return meta

    def to_dict(self) -> dict[str, Any]:
        """Serialize graph to a plain dict (JSON/YAML safe)."""
        return {
            "nodes": [dataclasses.asdict(n) for n in self._nodes.values()],
            "edges": [dataclasses.asdict(e) for e in self._edges],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrgGraph:
        graph = cls()
        for n in data.get("nodes", []):
            graph.add_node(OrgNode(**n))
        for e in data.get("edges", []):
            graph.add_edge(OrgEdge(**e))
        return graph
