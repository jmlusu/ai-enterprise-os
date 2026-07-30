"""Documentation Generator — produces entity documentation pages.

Generates Markdown doc pages for executives, departments, specialists, and
workflows into ``generated/docs/``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_company.models.company import (
    CompanyManifest,
    CompanyRegistry,
    DepartmentData,
    ExecutiveEntry,
    SpecialistEntry,
    WorkflowEntry,
)


class DocGenerator:
    """Generate documentation pages from registry data."""

    def __init__(
        self,
        registry: CompanyRegistry,
        manifest: CompanyManifest | None = None,
    ) -> None:
        self._registry = registry
        self._manifest = manifest or self._build_minimal_manifest()
        self._warnings: list[str] = []

    class Result:
        def __init__(self) -> None:
            self.pages: list[dict[str, Any]] = []
            self.warnings: list[str] = []

        def summary(self) -> dict[str, Any]:
            return {"pages": len(self.pages), "warnings": len(self.warnings)}

    def generate(self) -> Result:
        result = self.Result()
        company = self._manifest.name

        for ex in self._registry.executives:
            if not ex.name:
                continue
            page = self._render_executive(company, ex)
            result.pages.append(page)

        for dept_name, dept in self._registry.departments.items():
            page = self._render_department(company, dept_name, dept)
            result.pages.append(page)

        for spec in self._registry.specialists:
            if not spec.name:
                continue
            page = self._render_specialist(company, spec)
            result.pages.append(page)

        for wf in self._registry.workflows:
            if not wf.name:
                continue
            page = self._render_workflow(company, wf)
            result.pages.append(page)

        result.warnings.extend(self._warnings)
        return result

    def _render_executive(self, company: str, ex: ExecutiveEntry) -> dict[str, Any]:
        lines = [
            f"# {ex.name}",
            f"**Company:** {company}",
            f"**Role:** {ex.title or 'Executive'}",
            "",
            "## Responsibilities",
            "",
        ]
        if ex.responsibilities:
            for r in ex.responsibilities:
                lines.append(f"- {r}")
        lines.extend(["", "## Key Performance Indicators", ""])
        if ex.kpis:
            for k in ex.kpis:
                lines.append(f"- {k}")
        lines.append("")
        assert ex.name is not None  # guarded by caller
        slug = ex.name.lower().replace(" ", "_").replace(".", "")
        return {
            "title": ex.name,
            "slug": slug,
            "type": "executive",
            "markdown": "\n".join(lines),
        }

    def _render_department(
        self, company: str, name: str, dept: DepartmentData
    ) -> dict[str, Any]:
        title = name.replace("_", " ").title()
        lines = [
            f"# {title}",
            f"**Company:** {company}",
            "",
            "## Roles",
            "",
        ]
        for role in dept.roles:
            parts = [f"- **{role.title}**"]
            if role.description:
                parts.append(f": {role.description}")
            lines.append("".join(parts))
        lines.append("")
        slug = name.lower().replace(" ", "_").replace(".", "")
        return {
            "title": title,
            "slug": slug,
            "type": "department",
            "markdown": "\n".join(lines),
        }

    def _render_specialist(self, company: str, spec: SpecialistEntry) -> dict[str, Any]:
        lines = [
            f"# {spec.name}",
            f"**Company:** {company}",
            f"**Expertise:** {spec.expertise or ''}",
            "",
        ]
        assert spec.name is not None  # guarded by caller
        slug = spec.name.lower().replace(" ", "_").replace(".", "")
        return {
            "title": spec.name,
            "slug": slug,
            "type": "specialist",
            "markdown": "\n".join(lines),
        }

    def _render_workflow(self, company: str, wf: WorkflowEntry) -> dict[str, Any]:
        lines = [
            f"# {wf.name}",
            f"**Company:** {company}",
            f"**Description:** {wf.description or ''}",
            "",
            "## Steps",
            "",
        ]
        if wf.steps:
            for s in wf.steps:
                lines.append(f"- {s}")
        lines.append("")
        assert wf.name is not None  # guarded by caller
        slug = wf.name.lower().replace(" ", "_").replace(".", "")
        return {
            "title": wf.name,
            "slug": slug,
            "type": "workflow",
            "markdown": "\n".join(lines),
        }

    def write_artifacts(self, result: Result, output_dir: Path) -> list[Path]:
        created: list[Path] = []
        docs_dir = output_dir / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)

        for page in result.pages:
            filename = f"{page['type']}__{page['slug']}.md"
            path = docs_dir / filename
            path.write_text(page["markdown"], encoding="utf-8")
            created.append(path)

        # Sidebar / index
        index_lines = [
            "# Documentation Index\n",
            f"Total pages: {len(result.pages)}\n",
            "",
        ]
        for page in result.pages:
            index_lines.append(
                f"- [{page['title']}]({page['type']}__{page['slug']}.md) — *{page['type']}*"
            )
        index_path = docs_dir / "INDEX.md"
        index_path.write_text("\n".join(index_lines), encoding="utf-8")
        created.append(index_path)

        return created

    def validate(self) -> list[str]:
        errors: list[str] = []
        if (
            not self._registry.executives
            and not self._registry.departments
            and not self._registry.specialists
            and not self._registry.workflows
        ):
            errors.append("No entities found to generate documentation for")
        return errors

    def _build_minimal_manifest(self) -> CompanyManifest:
        return CompanyManifest(
            name=self._registry.vision.company_name
            or self._registry.vision.name
            or "Company",
            company_name=self._registry.vision.company_name
            or self._registry.vision.name,
            description=self._registry.vision.description or "",
        )
