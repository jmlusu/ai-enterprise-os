"""CLI-facing wrapper for the Organization Generator and Board Generator.

The :class:`CompanyGenerator` provides high-level methods that can be
called from CLI commands, with file output, logging, and integration
into the broader generation pipeline.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from ai_company.company.board_generator import BoardGenerator, BoardResult
from ai_company.company.organization import OrganizationGenerator, OrganizationResult
from ai_company.models.company import CompanyRegistry
from ai_company.registry.registry import RegistryEngine

logger = logging.getLogger(__name__)


class CompanyGenerator:
    """High-level generator for organization artifacts.

    Usage::

        gen = CompanyGenerator()
        result = gen.generate()

    Args:
        company_dir: Path to the company YAML directory.
        output_dir: Path to write generated artifacts.
        registry: Optionally pass a pre-loaded registry.
    """

    def __init__(
        self,
        company_dir: str | Path = Path("company"),
        output_dir: str | Path = Path("generated"),
        registry: CompanyRegistry | None = None,
    ) -> None:
        self._company_dir = Path(company_dir)
        self._output_dir = Path(output_dir)
        self._registry = registry

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(self) -> OrganizationResult:
        """Load registry, generate the organization, and write artifacts."""
        registry = self._load_registry()

        org_gen = OrganizationGenerator(registry)
        result = org_gen.generate()

        # Write artifacts
        self._write_artifacts(result)

        return result

    def generate_from_registry(self, registry: CompanyRegistry) -> OrganizationResult:
        """Generate from an already-loaded registry (no re-load)."""
        self._registry = registry
        org_gen = OrganizationGenerator(registry)
        result = org_gen.generate()
        self._write_artifacts(result)
        return result

    # ------------------------------------------------------------------
    # Artifact writers
    # ------------------------------------------------------------------

    def _write_artifacts(self, result: OrganizationResult) -> None:
        self._ensure_dirs()

        # JSON export
        json_path = self._output_dir / "organization.json"
        OrganizationGenerator.export_json(result.graph, json_path)

        # YAML export
        yaml_path = self._output_dir / "organization.yaml"
        OrganizationGenerator.export_yaml(result.graph, yaml_path)

        # Summary report
        summary_path = self._output_dir / "organization_summary.yaml"
        summary_path.write_text(
            yaml.dump(
                {"organization": result.summary(), "warnings": result.warnings},
                default_flow_style=False,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        # Roles export
        roles_path = self._output_dir / "organization_roles.json"
        roles_path.write_text(
            json.dumps(result.roles, indent=2, default=str), encoding="utf-8"
        )

        # Markdown report
        md_path = self._output_dir / "docs" / "ORGANIZATION.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(self._render_markdown(result), encoding="utf-8")

        logger.info("Wrote organization artifacts to %s", self._output_dir)

    def _ensure_dirs(self) -> None:
        (self._output_dir / "docs").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _render_markdown(result: OrganizationResult) -> str:
        """Render a human-readable organization report in Markdown."""
        s = result.summary()
        lines = [
            "# Organization Structure",
            "",
            f"**Generated:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Summary",
            "",
            f"- **Total Nodes:** {s['nodes']}",
            f"- **Total Edges:** {s['edges']}",
            f"- **Max Depth:** {s['max_depth']} levels",
            f"- **Total Roles:** {s['roles']}",
            f"- **Warnings:** {s['warnings']}",
            "",
            "## Node Type Breakdown",
            "",
        ]
        for ntype, count in sorted(s["node_types"].items()):
            lines.append(f"- **{ntype}:** {count}")

        lines.extend(["", "## Node Inventory", ""])
        for nid in sorted(result.graph.nodes):
            node = result.graph.nodes[nid]
            lines.append(
                f"- `{node.id}` — **{node.name}** ({node.title}) "
                f"[{node.node_type}, level {node.level}]"
            )

        lines.extend(["", "## Edge Inventory", ""])
        by_type: dict[str, list[str]] = {}
        for edge in result.graph.edges:
            by_type.setdefault(edge.edge_type, []).append(
                f"`{edge.source_id}` → `{edge.target_id}`"
            )
        for etype, edges in sorted(by_type.items()):
            lines.append(f"### {etype} ({len(edges)})")
            for e in edges[:20]:  # cap at 20 per type
                lines.append(f"- {e}")
            if len(edges) > 20:
                lines.append(f"- *… and {len(edges) - 20} more*")

        if result.warnings:
            lines.extend(["", "## Warnings", ""])
            for w in result.warnings:
                lines.append(f"- ⚠ {w}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Registry loading
    # ------------------------------------------------------------------

    def _load_registry(self) -> CompanyRegistry:
        if self._registry is not None:
            return self._registry

        engine = RegistryEngine()
        result = engine.load(self._company_dir, config_dir=Path("config/company"))
        if not result.success or result.registry is None:
            msg = "; ".join(result.errors) if result.errors else "Unknown error"
            raise RuntimeError(f"Failed to load registry: {msg}")
        self._registry = result.registry
        return self._registry

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """Validate the registry can produce a valid organization."""
        errors: list[str] = []
        try:
            registry = self._load_registry()
        except RuntimeError as e:
            return [str(e)]

        if not registry.executives:
            errors.append("No executives defined — organization has no leadership")
        if not registry.departments:
            errors.append("No departments defined — organization has no structure")

        return errors

    # ------------------------------------------------------------------
    # Board generation
    # ------------------------------------------------------------------

    def generate_board(self) -> BoardResult:
        """Generate board artifacts from the loaded registry."""
        registry = self._load_registry()
        board_gen = BoardGenerator(registry, config_dir=Path("config/board"))
        result = board_gen.generate()
        self._write_board_artifacts(result)
        return result

    def _write_board_artifacts(self, result: BoardResult) -> None:
        self._ensure_dirs()
        generator = BoardGenerator(self._load_registry())
        generator.write_artifacts(result, self._output_dir)

    def validate_board(self) -> list[str]:
        """Validate that the registry can produce board artifacts."""
        try:
            registry = self._load_registry()
        except RuntimeError as e:
            return [str(e)]
        board_gen = BoardGenerator(registry, config_dir=Path("config/board"))
        return board_gen.validate()
