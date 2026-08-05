"""CLI-facing wrapper for all company-level generators.

The :class:`CompanyGenerator` provides high-level methods that can be
called from CLI commands, with file output, logging, and integration
into the broader generation pipeline.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from ai_company.company.board_generator import BoardGenerator, BoardResult
from ai_company.company.company_docs_generator import CompanyDocsGenerator
from ai_company.company.department_generator import DepartmentGenerator
from ai_company.company.doc_generator import DocGenerator
from ai_company.company.executive_generator import ExecutiveGenerator
from ai_company.company.graph_exporter import GraphExporter
from ai_company.company.organization import OrganizationGenerator, OrganizationResult
from ai_company.company.prompt_generator import PromptLibraryGenerator
from ai_company.company.specialist_generator import SpecialistGenerator
from ai_company.company.workflow_generator import WorkflowGenerator
from ai_company.models.company import CompanyManifest, CompanyRegistry
from ai_company.registry.registry import RegistryEngine

logger = logging.getLogger(__name__)


class GenerateAllResult:
    """Aggregated result of running every company generator.

    Attributes:
        summaries: Per-generator summary dicts keyed by generator name.
        warnings: Collected warnings from all generators.
        created_files: Paths of every file written to disk.
    """

    def __init__(self) -> None:
        self.summaries: dict[str, dict[str, Any]] = {}
        self.warnings: list[str] = []
        self.created_files: list[Path] = []

    def summary(self) -> dict[str, Any]:
        total_files = sum(
            s.get("files", 0) for s in self.summaries.values() if isinstance(s, dict)
        )
        return {
            "generators": len(self.summaries),
            "files": len(self.created_files),
            "total_files": total_files,
            "warnings": len(self.warnings),
        }


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
        self._warnings: list[str] = []

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

    def generate_all(self) -> GenerateAllResult:
        """Run every generator and write all artifacts.

        Executes, in order: organization, board, executives, departments,
        specialists, workflows, prompts, docs, graph export, and company
        docs. Each sub-generator's summary and created files are aggregated
        into a single :class:`GenerateAllResult`.
        """
        result = GenerateAllResult()
        registry = self._load_registry()
        manifest = self._load_manifest()

        def _run(
            name: str,
            gen_result: Any,
            written: list[Path] | None = None,
        ) -> None:
            result.summaries[name] = gen_result.summary()
            warnings = getattr(gen_result, "warnings", None)
            if warnings:
                result.warnings.extend(warnings)
            if written:
                result.created_files.extend(written)

        # 1. Organization structure
        org_gen = OrganizationGenerator(registry)
        org_result = org_gen.generate()
        self._write_artifacts(org_result)
        _run("organization", org_result)

        # 2. Board
        board_gen = BoardGenerator(registry, config_dir=Path("config/board"))
        board_result = board_gen.generate()
        written = board_gen.write_artifacts(board_result, self._output_dir)
        _run("board", board_result, written)

        # 3. Executives
        exec_gen = ExecutiveGenerator(registry, manifest)
        exec_result = exec_gen.generate()
        written = exec_gen.write_artifacts(exec_result, self._output_dir)
        _run("executives", exec_result, written)

        # 4. Departments
        dept_gen = DepartmentGenerator(registry, manifest)
        dept_result = dept_gen.generate()
        written = dept_gen.write_artifacts(dept_result, self._output_dir)
        _run("departments", dept_result, written)

        # 5. Specialists
        spec_gen = SpecialistGenerator(registry, manifest)
        spec_result = spec_gen.generate()
        written = spec_gen.write_artifacts(spec_result, self._output_dir)
        _run("specialists", spec_result, written)

        # 6. Workflows
        wf_gen = WorkflowGenerator(registry)
        wf_result = wf_gen.generate()
        written = wf_gen.write_artifacts(wf_result, self._output_dir)
        _run("workflows", wf_result, written)

        # 7. Prompts
        prompt_gen = PromptLibraryGenerator(registry, manifest)
        prompt_result = prompt_gen.generate()
        written = prompt_gen.write_artifacts(prompt_result, self._output_dir)
        _run("prompts", prompt_result, written)

        # 8. Docs
        doc_gen = DocGenerator(registry, manifest)
        doc_result = doc_gen.generate()
        written = doc_gen.write_artifacts(doc_result, self._output_dir)
        _run("docs", doc_result, written)

        # 9. Graph export
        graph_gen = GraphExporter(registry)
        graph_result = graph_gen.generate()
        written = graph_gen.write_artifacts(graph_result, self._output_dir)
        _run("graph", graph_result, written)

        # 10. Company docs (deterministic top-level documents)
        docs_gen = CompanyDocsGenerator(
            registry,
            manifest=manifest,
            config_dir=Path("config"),
            graph=org_result.graph,
        )
        docs_result = docs_gen.generate()
        written = docs_gen.write_artifacts(docs_result, self._output_dir)
        _run("company_docs", docs_result, written)

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

    # ------------------------------------------------------------------
    # Executive generation
    # ------------------------------------------------------------------

    def generate_executives(self) -> ExecutiveGenerator.Result:
        """Generate executive artifact packages from the loaded registry."""
        registry = self._load_registry()
        manifest = self._load_manifest()
        exec_gen = ExecutiveGenerator(registry, manifest)
        result = exec_gen.generate()
        exec_gen.write_artifacts(result, self._output_dir)
        return result

    def validate_executives(self) -> list[str]:
        """Validate that the registry can produce executive artifacts."""
        try:
            registry = self._load_registry()
        except RuntimeError as e:
            return [str(e)]
        exec_gen = ExecutiveGenerator(registry)
        return exec_gen.validate()

    # ------------------------------------------------------------------
    # Department generation (stub for Phase 4)
    # ------------------------------------------------------------------

    def generate_departments(self) -> DepartmentGenerator.Result:
        """Generate department artifacts from the manifest and registry."""
        registry = self._load_registry()
        manifest = self._load_manifest()
        dept_gen = DepartmentGenerator(registry, manifest)
        result = dept_gen.generate()
        dept_gen.write_artifacts(result, self._output_dir)
        return result

    def validate_departments(self) -> list[str]:
        """Validate that the manifest has departments defined."""
        try:
            registry = self._load_registry()
        except RuntimeError as e:
            return [str(e)]
        manifest = self._load_manifest()
        dept_gen = DepartmentGenerator(registry, manifest)
        return dept_gen.validate()

    # ------------------------------------------------------------------
    # Specialist generation (stub for Phase 5)
    # ------------------------------------------------------------------

    def generate_specialists(self) -> SpecialistGenerator.Result:
        """Generate specialist agent artifacts from the registry."""
        registry = self._load_registry()
        manifest = self._load_manifest()
        spec_gen = SpecialistGenerator(registry, manifest)
        result = spec_gen.generate()
        spec_gen.write_artifacts(result, self._output_dir)
        return result

    def validate_specialists(self) -> list[str]:
        """Validate that the registry has specialists defined."""
        try:
            registry = self._load_registry()
        except RuntimeError as e:
            return [str(e)]
        spec_gen = SpecialistGenerator(registry)
        return spec_gen.validate()

    # ------------------------------------------------------------------
    # Workflow generation (stub for Phase 6)
    # ------------------------------------------------------------------

    def generate_workflows(self) -> WorkflowGenerator.Result:
        """Generate workflow artifacts from the registry."""
        registry = self._load_registry()
        wf_gen = WorkflowGenerator(registry)
        result = wf_gen.generate()
        wf_gen.write_artifacts(result, self._output_dir)
        return result

    def validate_workflows(self) -> list[str]:
        """Validate that the registry has workflows defined."""
        try:
            registry = self._load_registry()
        except RuntimeError as e:
            return [str(e)]
        wf_gen = WorkflowGenerator(registry)
        return wf_gen.validate()

    # ------------------------------------------------------------------
    # Prompt generation (stub for Phase 7)
    # ------------------------------------------------------------------

    def generate_prompts(self) -> PromptLibraryGenerator.Result:
        """Generate prompt library artifacts from the registry."""
        registry = self._load_registry()
        manifest = self._load_manifest()
        prompt_gen = PromptLibraryGenerator(registry, manifest)
        result = prompt_gen.generate()
        prompt_gen.write_artifacts(result, self._output_dir)
        return result

    def validate_prompts(self) -> list[str]:
        """Validate that there are entities to generate prompts for."""
        try:
            registry = self._load_registry()
        except RuntimeError as e:
            return [str(e)]
        prompt_gen = PromptLibraryGenerator(registry)
        return prompt_gen.validate()

    # ------------------------------------------------------------------
    # Documentation generation (stub for Phase 8)
    # ------------------------------------------------------------------

    def generate_docs(self) -> DocGenerator.Result:
        """Generate documentation artifacts from the registry."""
        registry = self._load_registry()
        manifest = self._load_manifest()
        doc_gen = DocGenerator(registry, manifest)
        result = doc_gen.generate()
        doc_gen.write_artifacts(result, self._output_dir)
        return result

    def validate_docs(self) -> list[str]:
        """Validate that there are entities to generate docs for."""
        try:
            registry = self._load_registry()
        except RuntimeError as e:
            return [str(e)]
        doc_gen = DocGenerator(registry)
        return doc_gen.validate()

    def generate_graph_export(self) -> GraphExporter.Result:
        """Generate graph export artifacts (Mermaid, enriched JSON)."""
        return GraphExporter(self._load_registry()).generate()

    def validate_graph_export(self) -> list[str]:
        """Validate that there are entities to build a graph from."""
        try:
            registry = self._load_registry()
        except RuntimeError as e:
            return [str(e)]
        return GraphExporter(registry).validate()

    def _warn_not_implemented(self, method: str) -> None:
        self._warnings.append(
            f"{method} is not yet implemented — no artifacts generated"
        )

    def _load_manifest(self) -> CompanyManifest:
        manifest_path = Path("config/company/company.yaml")
        if manifest_path.exists():
            try:
                return CompanyManifest.load(manifest_path)
            except (FileNotFoundError, ValueError):
                pass
        reg = self._load_registry()
        return CompanyManifest(
            name=reg.vision.company_name or reg.vision.name or "Company",
            company_name=reg.vision.company_name or reg.vision.name,
            description=reg.vision.description or "",
        )
