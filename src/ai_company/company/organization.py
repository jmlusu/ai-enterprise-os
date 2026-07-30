"""Main orchestrator for the Organization Generator.

The :class:`OrganizationGenerator` composes the hierarchy builder, role
generator, relationship resolver, and reporting structure into a single
pipeline that produces a complete :class:`~ai_company.company.models.OrgGraph`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from ai_company.company.hierarchy import HierarchyBuilder
from ai_company.company.models import OrgGraph, OrgMetadata
from ai_company.company.relationships import RelationshipResolver
from ai_company.company.reporting import ReportingStructure
from ai_company.company.roles import RoleGenerator
from ai_company.models.company import CompanyRegistry

logger = logging.getLogger(__name__)


class OrganizationGenerator:
    """Composable pipeline that generates a complete organizational model.

    Usage::

        gen = OrganizationGenerator(registry)
        result = gen.generate()
        print(result.metadata.warnings)

    Args:
        registry: A loaded :class:`~ai_company.models.company.CompanyRegistry`.
        graph: An optional pre-populated graph (for re-generation).
    """

    def __init__(
        self,
        registry: CompanyRegistry,
        graph: OrgGraph | None = None,
    ) -> None:
        self._registry = registry
        self._graph = graph or OrgGraph()
        self._metadata: OrgMetadata | None = None
        self._roles: list[dict[str, Any]] = []
        self._warnings: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self) -> OrganizationResult:
        """Execute the full organization generation pipeline.

        Pipeline steps:

        1. :class:`HierarchyBuilder` — build the org tree from registry
        2. :class:`RoleGenerator` — enrich role definitions
        3. :class:`RelationshipResolver` — connect entities
        4. :class:`ReportingStructure` — validate and compute metadata

        Returns:
            An :class:`OrganizationResult` with the graph, roles, and metadata.
        """
        logger.info("Starting organization generation...")

        # Step 1: Build hierarchy
        hierarchy = HierarchyBuilder(self._registry)
        self._graph = hierarchy.build()

        # Step 2: Generate roles
        role_gen = RoleGenerator(self._registry, self._graph)
        self._roles = role_gen.generate_all()

        # Step 3: Resolve relationships
        resolver = RelationshipResolver(self._registry, self._graph)
        self._graph = resolver.resolve_all()
        self._warnings.extend(resolver.warnings)

        # Step 4: Analyse reporting structure
        reporting = ReportingStructure(self._graph)
        self._metadata = reporting.analyse()
        self._warnings.extend(self._metadata.warnings)

        logger.info(
            "Organization generation complete: %d nodes, %d edges, %d roles",
            len(self._graph.nodes),
            len(self._graph.edges),
            len(self._roles),
        )

        return OrganizationResult(
            graph=self._graph,
            roles=list(self._roles),
            metadata=self._metadata,
            warnings=list(self._warnings),
        )

    def generate_hierarchy_only(self) -> OrgGraph:
        """Shortcut — build just the hierarchy tree without enrichment."""
        hierarchy = HierarchyBuilder(self._registry)
        return hierarchy.build()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    @staticmethod
    def export_json(graph: OrgGraph, output_path: str | Path) -> Path:
        """Export the organization graph as JSON."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = graph.to_dict()
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        logger.info("Exported organization JSON to %s", path)
        return path

    @staticmethod
    def export_yaml(graph: OrgGraph, output_path: str | Path) -> Path:
        """Export the organization graph as YAML."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = graph.to_dict()
        path.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        logger.info("Exported organization YAML to %s", path)
        return path


class OrganizationResult:
    """The result of a full organization generation run."""

    def __init__(
        self,
        graph: OrgGraph,
        roles: list[dict[str, Any]],
        metadata: OrgMetadata,
        warnings: list[str],
    ) -> None:
        self.graph = graph
        self.roles = roles
        self.metadata = metadata
        self.warnings = warnings

    def summary(self) -> dict[str, Any]:
        return {
            "nodes": self.metadata.total_nodes,
            "edges": self.metadata.total_edges,
            "max_depth": self.metadata.max_depth,
            "roles": len(self.roles),
            "warnings": len(self.warnings),
            "node_types": dict(self.metadata.node_type_counts),
        }
