"""Graph Export Enhancement — Mermaid diagram and enriched JSON exports.

Generates Mermaid flowchart diagrams and enriched JSON exports from
the registry, writing them into ``generated/graph/``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_company.models.company import CompanyRegistry

MERMAID_THEME = """---
title: Organization Chart
---
"""


class GraphExporter:
    """Generate enhanced graph exports (Mermaid, enriched JSON)."""

    def __init__(self, registry: CompanyRegistry) -> None:
        self._registry = registry

    class Result:
        def __init__(self) -> None:
            self.mermaid: str = ""
            self.warnings: list[str] = []

        def summary(self) -> dict[str, Any]:
            return {
                "mermaid_length": len(self.mermaid),
                "warnings": len(self.warnings),
            }

    def generate(self) -> Result:
        result = self.Result()
        lines: list[str] = [MERMAID_THEME, "flowchart TD"]

        # Executives
        for ex in self._registry.executives:
            if not ex.name:
                continue
            safe_id = ex.name.replace(" ", "_").replace(".", "")
            label = ex.name.replace('"', "'")
            lines.append(f'    {safe_id}["{label}"]')

        # Departments as subgraphs
        for dept_name in self._registry.departments:
            safe_id = f"dept_{dept_name.replace(' ', '_')}"
            label = dept_name.replace("_", " ").title()
            lines.append(f'    {safe_id}["{label}"]')

        # Workflows
        for wf in self._registry.workflows:
            if not wf.name:
                continue
            safe_id = f"wf_{wf.name.replace(' ', '_')}"
            label = wf.name.replace('"', "'")
            lines.append(f'    {safe_id}["{label}"]')

        # Hierarchy edges: executives → departments
        for ex in self._registry.executives:
            if not ex.name:
                continue
            ex_id = ex.name.replace(" ", "_").replace(".", "")
            dept = ex.department or ""
            if dept in self._registry.departments:
                dept_id = f"dept_{dept.replace(' ', '_')}"
                lines.append(f"    {ex_id} --> {dept_id}")

        # Reports-to edges
        for ex in self._registry.executives:
            if not ex.name or not ex.reports_to:
                continue
            ex_id = ex.name.replace(" ", "_").replace(".", "")
            rep_id = ex.reports_to.replace(" ", "_").replace(".", "")
            lines.append(f"    {ex_id} --> {rep_id}")

        result.mermaid = "\n".join(lines) + "\n"
        return result

    def write_artifacts(self, result: Result, output_dir: Path) -> list[Path]:
        created: list[Path] = []
        graph_dir = output_dir / "graph"
        graph_dir.mkdir(parents=True, exist_ok=True)

        mermaid_path = graph_dir / "org_chart.mmd"
        mermaid_path.write_text(result.mermaid, encoding="utf-8")
        created.append(mermaid_path)

        # Enriched JSON export
        json_data = self._build_json_export()
        json_path = graph_dir / "graph_enriched.json"
        json_path.write_text(
            __import__("json").dumps(json_data, indent=2, default=str),
            encoding="utf-8",
        )
        created.append(json_path)

        return created

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self._registry.executives and not self._registry.departments:
            errors.append("No nodes found to build a graph from")
        return errors

    def _build_json_export(self) -> dict[str, Any]:
        return {
            "executives": [
                {
                    "name": ex.name,
                    "title": ex.title,
                    "department": ex.department,
                    "reports_to": ex.reports_to,
                    "status": ex.status,
                }
                for ex in self._registry.executives
                if ex.name
            ],
            "departments": list(self._registry.departments.keys()),
            "specialists": [s.name for s in self._registry.specialists if s.name],
            "workflows": [
                {"name": wf.name, "steps": len(wf.steps)}
                for wf in self._registry.workflows
                if wf.name
            ],
        }
