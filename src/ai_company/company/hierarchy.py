"""Build the company hierarchy tree from registry data.

The :class:`HierarchyBuilder` walks the executive, department, and role
data in a :class:`~ai_company.models.company.CompanyRegistry` and produces
a tree of :class:`~ai_company.company.models.OrgNode` instances with
correct level assignments.
"""

from __future__ import annotations

import logging
from typing import Any

from ai_company.company.models import OrgEdge, OrgGraph, OrgNode
from ai_company.models.company import CompanyRegistry

logger = logging.getLogger(__name__)


class HierarchyError(Exception):
    """Raised when hierarchy construction fails."""


class HierarchyBuilder:
    """Builds a level-annotated organization tree from the registry.

    Level conventions::

        0 — Board of Directors
        1 — C-suite / CEO direct reports
        2 — Senior leadership / VP / Director
        3 — Managers / team leads
        4 — Individual contributors / specialists
    """

    def __init__(self, registry: CompanyRegistry) -> None:
        self._registry = registry
        self._graph = OrgGraph()
        self._level_map: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> OrgGraph:
        """Run the full hierarchy build.

        Returns:
            An :class:`OrgGraph` with all nodes and edges populated.

        Raises:
            HierarchyError: If the build encounters an inconsistency that
                prevents completion.
        """
        self._graph = OrgGraph()
        self._level_map = {}

        try:
            self._build_board_level()
            self._build_executive_level()
            self._build_department_level()
            self._build_role_level()
            self._build_specialist_level()
            self._resolve_levels()
        except Exception as exc:
            raise HierarchyError(f"Hierarchy build failed: {exc}") from exc

        logger.info(
            "Built hierarchy: %d nodes, %d edges, max depth=%d",
            len(self._graph.nodes),
            len(self._graph.edges),
            self._compute_max_depth(),
        )
        return self._graph

    # ------------------------------------------------------------------
    # Level builders
    # ------------------------------------------------------------------

    def _make_id(self, prefix: str, name: str) -> str:
        """Create a stable, URL-safe node identifier."""
        safe = name.strip().lower().replace(" ", "_").replace(".", "")
        return f"{prefix}:{safe}"

    def _add_node(
        self,
        node_id: str,
        name: str,
        title: str,
        node_type: str,
        level: int,
        department: str = "",
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> OrgNode:
        node = OrgNode(
            id=node_id,
            name=name,
            title=title,
            node_type=node_type,
            level=level,
            department=department,
            parent_id=parent_id,
            metadata=metadata or {},
        )
        self._graph.add_node(node)
        self._level_map[node_id] = level
        return node

    def _add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str = "reports_to",
    ) -> None:
        self._graph.add_edge(OrgEdge(source_id, target_id, edge_type))

    def _build_board_level(self) -> None:
        """Level 0 — Board of Directors."""
        board_id = self._make_id("board", "board_of_directors")
        self._add_node(
            board_id,
            "Board of Directors",
            "Board of Directors",
            "board",
            level=0,
        )

        for member in self._registry.board:
            safe_name = member.name or "unnamed"
            member_id = self._make_id("board", safe_name)
            self._add_node(
                member_id,
                safe_name,
                member.role or "Board Member",
                "board",
                level=0,
                parent_id=board_id,
            )
            self._add_edge(member_id, board_id, "member_of")

        for bm in self._registry.board_members:
            safe_name = bm.name
            member_id = self._make_id("board", safe_name)
            self._add_node(
                member_id,
                safe_name,
                bm.role or "Board Member",
                "board",
                level=0,
                parent_id=board_id,
                metadata={
                    "term_start": bm.term_start or "",
                    "term_end": bm.term_end or "",
                    "independent": bm.independent,
                    "committees": list(bm.committees),
                },
            )
            self._add_edge(member_id, board_id, "member_of")

    def _build_executive_level(self) -> None:
        """Level 0-1 — Executives.

        The CEO sits at level 0 (alongside board).  Other C-suite and
        VP-level executives are placed at level 1.  The `reports_to`
        field determines the parent relationship.
        """
        ceo_id: str | None = None
        exec_ids: dict[str, str] = {}

        # First pass — create nodes
        for ex in self._registry.executives:
            if not ex.name:
                continue
            safe_name = ex.name
            node_id = self._make_id("exec", safe_name)
            exec_ids[safe_name] = node_id

            title_lower = (ex.title or "").lower()
            is_ceo = bool(
                title_lower
                and (
                    title_lower == "ceo"
                    or "chief executive officer" in title_lower
                    or title_lower.startswith("ceo")
                    or "ceo" in title_lower.split()
                )
            )
            level = 0 if is_ceo else 1

            self._add_node(
                node_id,
                safe_name,
                ex.title or "Executive",
                "executive",
                level=level,
                department=ex.department or "",
                metadata={
                    "status": ex.status or "active",
                    "responsibilities": list(ex.responsibilities),
                    "kpis": list(ex.kpis),
                    "budget_authority": ex.budget_authority,
                    "email": ex.email or "",
                },
            )

            if is_ceo:
                ceo_id = node_id

        # Second pass — edges (reports_to)
        for ex in self._registry.executives:
            if not ex.name:
                continue
            source_id = exec_ids[ex.name]

            if ex.reports_to:
                # Map reports_to to an existing executive or the board
                target_name = ex.reports_to
                # Check if it's an executive name
                target_id = exec_ids.get(target_name)
                if target_id is None:
                    # Maybe it's the board
                    if "board" in target_name.lower():
                        target_id = self._make_id("board", "board_of_directors")
                    else:
                        # Unresolved — link to board as fallback
                        target_id = self._make_id("board", "board_of_directors")
                self._add_edge(source_id, target_id, "reports_to")
            elif ceo_id and source_id != ceo_id:
                # Default: report to CEO
                self._add_edge(source_id, ceo_id, "reports_to")

    def _build_department_level(self) -> None:
        """Level 1 — Departments.

        Each department becomes a node linked to its head executive
        (if one can be identified).
        """
        # Build a map: department_name -> executive node id
        dept_to_exec: dict[str, str] = {}
        for ex in self._registry.executives:
            if ex.name and ex.department:
                dept_to_exec[ex.department] = self._make_id("exec", ex.name)

        for dept_name, dept_data in self._registry.departments.items():
            dept_id = self._make_id("dept", dept_name)
            parent_id = dept_to_exec.get(dept_name)

            self._add_node(
                dept_id,
                dept_data.name,
                f"Department: {dept_data.name}",
                "department",
                level=1,
                parent_id=parent_id,
            )

            if parent_id:
                self._add_edge(dept_id, parent_id, "leads")

    def _build_role_level(self) -> None:
        """Level 2-3 — Roles within each department."""
        for dept_name, dept_data in self._registry.departments.items():
            dept_id = self._make_id("dept", dept_name)
            for role in dept_data.roles:
                role_id = self._make_id("role", f"{dept_name}/{role.title}")
                self._add_node(
                    role_id,
                    role.title,
                    role.description or role.title,
                    "role",
                    level=2,
                    department=dept_name,
                    parent_id=dept_id,
                )
                self._add_edge(role_id, dept_id, "member_of")

    def _build_specialist_level(self) -> None:
        """Level 3 — Specialists (individual contributors / AI agents)."""
        for spec in self._registry.specialists:
            if not spec.name:
                continue
            spec_id = self._make_id("specialist", spec.name)
            self._add_node(
                spec_id,
                spec.name,
                spec.expertise or "Specialist",
                "specialist",
                level=3,
            )

    # ------------------------------------------------------------------
    # Post-processing
    # ------------------------------------------------------------------

    def _resolve_levels(self) -> None:
        """Walk the graph to assign accurate depths.

        Uses a BFS from root nodes (level 0) to propagate levels.
        This catches any nodes whose level was set optimistically but
        should be deeper due to reporting chains.
        """
        # Find roots — nodes that are level 0 or have no incoming edges
        roots = [
            nid
            for nid, node in self._graph.nodes.items()
            if node.level == 0 or not self._graph.parents_of(nid)
        ]

        from collections import deque

        queue: deque[tuple[str, int]] = deque()
        visited: set[str] = set()

        for root in roots:
            queue.append((root, 0))
            visited.add(root)

        while queue:
            nid, level = queue.popleft()
            node = self._graph.get_node(nid)
            if node is None:
                continue
            # Update level if this path gives a deeper assignment
            if level > node.level:
                updated = OrgNode(
                    id=node.id,
                    name=node.name,
                    title=node.title,
                    node_type=node.node_type,
                    level=level,
                    department=node.department,
                    parent_id=node.parent_id,
                    metadata=node.metadata,
                )
                self._graph.add_node(updated)
                self._level_map[nid] = level

            for child in self._graph.children_of(nid):
                if child.id not in visited:
                    visited.add(child.id)
                    queue.append((child.id, level + 1))

    def _compute_max_depth(self) -> int:
        return max((n.level for n in self._graph.nodes.values()), default=0)

    @property
    def graph(self) -> OrgGraph:
        return self._graph
