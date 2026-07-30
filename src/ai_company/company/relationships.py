"""Establish all entity relationships across the organization.

The :class:`RelationshipResolver` connects executives, departments, roles,
specialists, and board members into a unified relationship graph.
"""

from __future__ import annotations

import logging

from ai_company.company.models import OrgEdge, OrgGraph, OrgNode
from ai_company.models.company import CompanyRegistry

logger = logging.getLogger(__name__)


class RelationshipError(Exception):
    """Raised when relationship resolution encounters an inconsistency."""


class RelationshipResolver:
    """Builds and validates all entity relationships.

    Relationship types produced::

        reports_to     — direct reporting line (e.g. CTO -> CEO)
        leads          — executive leads a department
        member_of      — person is a member of a group/committee
        communicates_with — cross-functional communication channel
        depends_on     — dependency between entities

    Args:
        registry: Loaded company registry.
        graph: The organization graph to enrich with relationships.
    """

    def __init__(
        self,
        registry: CompanyRegistry,
        graph: OrgGraph,
    ) -> None:
        self._registry = registry
        self._graph = graph
        self._warnings: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_all(self) -> OrgGraph:
        """Run all relationship resolvers and return the enriched graph."""
        self._warnings = []

        self._resolve_executive_department_links()
        self._resolve_board_committee_relationships()
        self._resolve_specialist_placements()
        self._resolve_workflow_relationships()
        self._resolve_cross_functional_relationships()

        logger.info(
            "Resolved relationships: %d edges, %d warning(s)",
            len(self._graph.edges),
            len(self._warnings),
        )
        return self._graph

    @property
    def warnings(self) -> list[str]:
        return list(self._warnings)

    # ------------------------------------------------------------------
    # Relationship builders
    # ------------------------------------------------------------------

    def _resolve_executive_department_links(self) -> None:
        """Ensure every executive is linked to their department."""
        for ex in self._registry.executives:
            if not ex.name or not ex.department:
                continue
            exec_id = self._make_id("exec", ex.name)
            dept_id = self._make_id("dept", ex.department)

            # Only add edge if both nodes exist in the graph
            if self._graph.get_node(exec_id) and self._graph.get_node(dept_id):
                # Check if edge already exists
                already = any(
                    e.source_id == dept_id
                    and e.target_id == exec_id
                    and e.edge_type == "leads"
                    for e in self._graph.edges
                )
                if not already:
                    self._graph.add_edge(OrgEdge(dept_id, exec_id, "leads"))

    def _resolve_board_committee_relationships(self) -> None:
        """Link board members to their committees."""
        for committee in self._registry.committees:
            committee_id = self._make_id("committee", committee.name)
            # Ensure committee node exists
            committee_node = self._graph.get_node(committee_id)
            if committee_node is None:
                committee_node = OrgNode(
                    id=committee_id,
                    name=committee.name,
                    title=f"Committee: {committee.purpose or committee.name}",
                    node_type="committee",
                    level=0,
                    metadata={
                        "purpose": committee.purpose,
                        "meeting_frequency": committee.meeting_frequency,
                    },
                )
                self._graph.add_node(committee_node)

            # Link chair
            if committee.chair:
                chair_id = self._make_id("board", committee.chair)
                if self._graph.get_node(chair_id):
                    self._graph.add_edge(OrgEdge(chair_id, committee_id, "chairs"))

            # Link members
            for member_name in committee.members:
                member_id = self._make_id("board", member_name)
                if self._graph.get_node(member_id):
                    already = any(
                        e.source_id == member_id
                        and e.target_id == committee_id
                        and e.edge_type == "member_of"
                        for e in self._graph.edges
                    )
                    if not already:
                        self._graph.add_edge(
                            OrgEdge(member_id, committee_id, "member_of")
                        )

    def _resolve_specialist_placements(self) -> None:
        """Place specialists into appropriate departments.

        A specialist is linked to a department if their expertise keywords
        match the department name or roles within it.  Otherwise they are
        left as unattached (the graph will flag them as orphans).
        """
        for spec in self._registry.specialists:
            if not spec.name:
                continue
            spec_id = self._make_id("specialist", spec.name)
            if self._graph.get_node(spec_id) is None:
                continue

            expertise_lower = (spec.expertise or "").lower()
            matched = False

            for dept_name in self._registry.departments:
                dept_id = self._make_id("dept", dept_name)
                if self._graph.get_node(dept_id) is None:
                    continue

                # Simple keyword matching
                if dept_name.lower() in expertise_lower or any(
                    dept_name.lower() in (role.title or "").lower()
                    for role in self._registry.departments[dept_name].roles
                ):
                    self._graph.add_edge(OrgEdge(spec_id, dept_id, "member_of"))
                    matched = True
                    break

            if not matched:
                self._warnings.append(
                    f"Specialist '{spec.name}' could not be placed in any department"
                )

    def _resolve_workflow_relationships(self) -> None:
        """Link workflows to the entities that participate in them."""
        for wf in self._registry.workflows:
            if not wf.name:
                continue
            wf_id = self._make_id("workflow", wf.name)

            # Ensure workflow node exists
            if self._graph.get_node(wf_id) is None:
                wf_node = OrgNode(
                    id=wf_id,
                    name=wf.name,
                    title=wf.description or f"Workflow: {wf.name}",
                    node_type="workflow",
                    level=0,
                )
                self._graph.add_node(wf_node)

            # Link steps to departments / roles mentioned in step text
            for step_text in wf.steps:
                step_lower = step_text.lower()
                for dept_name in self._registry.departments:
                    if dept_name.lower() in step_lower:
                        dept_id = self._make_id("dept", dept_name)
                        if self._graph.get_node(dept_id):
                            self._graph.add_edge(OrgEdge(wf_id, dept_id, "involves"))

    def _resolve_cross_functional_relationships(self) -> None:
        """Identify cross-functional communication channels.

        Currently heuristic: departments that share a common executive
        or whose workflows reference each other get ``communicates_with``
        edges.
        """
        # Departments whose executives share a reports_to chain
        exec_dept_map: dict[str, str] = {}
        for ex in self._registry.executives:
            if ex.name and ex.department:
                exec_dept_map[ex.name] = ex.department

        # Simple heuristic: if two departments have executives reporting
        # to the same person, add a communicates_with edge
        reports_to_depts: dict[str, set[str]] = {}
        for ex in self._registry.executives:
            if ex.name and ex.department and ex.reports_to:
                key = ex.reports_to
                if key not in reports_to_depts:
                    reports_to_depts[key] = set()
                reports_to_depts[key].add(ex.department)

        for depts in reports_to_depts.values():
            dept_list = list(depts)
            for i in range(len(dept_list)):
                for j in range(i + 1, len(dept_list)):
                    d1_id = self._make_id("dept", dept_list[i])
                    d2_id = self._make_id("dept", dept_list[j])
                    if self._graph.get_node(d1_id) and self._graph.get_node(d2_id):
                        self._graph.add_edge(OrgEdge(d1_id, d2_id, "communicates_with"))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_id(prefix: str, name: str) -> str:
        safe = name.strip().lower().replace(" ", "_").replace(".", "")
        return f"{prefix}:{safe}"
