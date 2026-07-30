"""Validate and analyse reporting structures.

The :class:`ReportingStructure` computes span of control, depth, chain
of command, and detects structural anomalies such as cycles and orphans.
"""

from __future__ import annotations

import logging
from typing import Any

from ai_company.company.models import OrgGraph, OrgMetadata

logger = logging.getLogger(__name__)


class ReportingError(Exception):
    """Raised when a structural anomaly is detected in the reporting graph."""


class ReportingStructure:
    """Analyses the reporting structure of an organization graph.

    Args:
        graph: The organization graph to analyse.
    """

    def __init__(self, graph: OrgGraph) -> None:
        self._graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(self) -> OrgMetadata:
        """Run all analyses and return aggregated metadata.

        Returns:
            :class:`OrgMetadata` with computed metrics, warnings, and
            detected anomalies.
        """
        meta = self._graph.compute_metadata()

        # Additional analyses specific to reporting health
        self._check_span_of_control_anomalies(meta)
        self._check_depth_consistency(meta)
        self._check_orphan_risk(meta)
        self._check_cycle_risk(meta)

        logger.info(
            "Reporting analysis complete: max_depth=%d, span_entries=%d, "
            "orphans=%d, cycles=%d",
            meta.max_depth,
            len(meta.span_of_control),
            len(meta.orphans),
            len(meta.cycles),
        )
        return meta

    # ------------------------------------------------------------------
    # Span of control
    # ------------------------------------------------------------------

    def get_span_of_control(self, node_id: str) -> int:
        """Return the number of direct reports for a given node."""
        return len(self._graph.children_of(node_id))

    def get_total_span_of_control(self, node_id: str) -> int:
        """Return total team size (direct + indirect reports)."""
        visited: set[str] = set()

        def _count(nid: str) -> int:
            total = 0
            for child in self._graph.children_of(nid):
                if child.id not in visited:
                    visited.add(child.id)
                    total += 1 + _count(child.id)
            return total

        return _count(node_id)

    def _check_span_of_control_anomalies(self, meta: OrgMetadata) -> None:
        """Warn if any manager has an extreme span of control."""
        for nid, span in meta.span_of_control.items():
            node = self._graph.get_node(nid)
            name = node.name if node else nid
            if span > 15:
                meta.warnings.append(
                    f"Wide span of control: '{name}' has {span} direct reports"
                )
            elif span == 0:
                # Only flag if the node is not an IC-level type
                if node and node.node_type in ("executive", "department"):
                    meta.warnings.append(
                        f"Zero span of control: '{name}' has no direct reports"
                    )

    # ------------------------------------------------------------------
    # Depth & chain of command
    # ------------------------------------------------------------------

    def get_reporting_chain(self, node_id: str) -> list[str]:
        """Return the chain of command from *node_id* to the top.

        Returns a list of node IDs starting with *node_id* and ending
        at a root node (level 0).
        """
        chain: list[str] = [node_id]
        current = node_id
        visited: set[str] = set()

        while True:
            parents = self._graph.parents_of(current)
            # Prefer "reports_to" edges
            reports_to_parents = [
                p.id
                for p in parents
                for e in self._graph.edges
                if e.source_id == current
                and e.target_id == p.id
                and e.edge_type == "reports_to"
            ]
            if reports_to_parents:
                next_id = reports_to_parents[0]
            elif parents:
                next_id = parents[0].id
            else:
                break

            if next_id in visited:
                break  # cycle prevention
            visited.add(next_id)
            chain.append(next_id)
            current = next_id

        return chain

    def get_all_reporting_chains(self) -> dict[str, list[str]]:
        """Return reporting chains for all nodes in the graph."""
        return {nid: self.get_reporting_chain(nid) for nid in self._graph.nodes}

    def _check_depth_consistency(self, meta: OrgMetadata) -> None:
        """Warn if the org depth exceeds a reasonable threshold."""
        if meta.max_depth > 8:
            meta.warnings.append(
                f"Deep hierarchy: {meta.max_depth} levels — may indicate "
                f"excessive layering"
            )

    # ------------------------------------------------------------------
    # Orphan detection
    # ------------------------------------------------------------------

    def find_orphans(self) -> list[str]:
        """Return node IDs that are disconnected from the reporting graph.

        An orphan is a node that has no incoming *or* outgoing ``reports_to``
        edges and is not at level 0.
        """
        orphans: list[str] = []
        for nid, node in self._graph.nodes.items():
            if node.level == 0:
                continue
            has_reports_to = any(
                e.source_id == nid and e.edge_type == "reports_to"
                for e in self._graph.edges
            )
            has_reported_by = any(
                e.target_id == nid and e.edge_type == "reports_to"
                for e in self._graph.edges
            )
            if not has_reports_to and not has_reported_by:
                orphans.append(nid)
        return orphans

    def _check_orphan_risk(self, meta: OrgMetadata) -> None:
        """Add orphan IDs to metadata and warn if any are found."""
        orphans = self.find_orphans()
        meta.orphans = list(set(meta.orphans + orphans))
        for oid in orphans:
            node = self._graph.get_node(oid)
            name = node.name if node else oid
            meta.warnings.append(f"Orphan node: '{name}' ({oid}) is disconnected")

    # ------------------------------------------------------------------
    # Cycle detection
    # ------------------------------------------------------------------

    def detect_cycles(self) -> list[list[str]]:
        """Detect all cycles in the reporting graph."""
        return self._graph.detect_cycles()

    def _check_cycle_risk(self, meta: OrgMetadata) -> None:
        """Add cycle info to metadata and warn if cycles exist."""
        cycles = self.detect_cycles()
        meta.cycles = cycles
        if cycles:
            names = []
            for cycle in cycles[:3]:  # report first 3 cycles
                names.append(" -> ".join(cycle))
            meta.warnings.append(
                f"Cycle(s) detected ({len(cycles)}): " + "; ".join(names)
            )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return a human-readable summary of the reporting structure."""
        meta = self.analyse()
        return {
            "total_nodes": meta.total_nodes,
            "total_edges": meta.total_edges,
            "max_depth": meta.max_depth,
            "node_type_breakdown": meta.node_type_counts,
            "managers": len(meta.span_of_control),
            "average_span": (
                sum(meta.span_of_control.values()) / len(meta.span_of_control)
                if meta.span_of_control
                else 0
            ),
            "orphans": meta.orphans,
            "cycles_found": len(meta.cycles),
            "warnings": meta.warnings,
        }
