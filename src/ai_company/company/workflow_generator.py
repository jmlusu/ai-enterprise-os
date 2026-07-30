"""Workflow Generator — produces per-workflow artifact packages.

Each workflow in the registry gets:
  - ``workflow.yaml`` — structured configuration
  - ``workflow.md`` — human-readable workflow document

All output goes to ``generated/workflows/{slug}/``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ai_company.models.company import CompanyRegistry


class WorkflowGenerator:
    """Generate per-workflow artifact packages from registry data."""

    def __init__(
        self,
        registry: CompanyRegistry,
        config_dir: str | Path = Path("config/workflows"),
    ) -> None:
        self._registry = registry
        self._config_dir = Path(config_dir)
        self._warnings: list[str] = []

    class Result:
        def __init__(self) -> None:
            self.workflows: list[dict[str, Any]] = []
            self.warnings: list[str] = []

        def summary(self) -> dict[str, Any]:
            return {
                "workflows": len(self.workflows),
                "warnings": len(self.warnings),
            }

    def generate(self) -> Result:
        result = self.Result()
        config = self._load_config()

        for entry in self._registry.workflows:
            if not entry.name:
                continue
            package = self._build_package(entry, config)
            result.workflows.append(package)

        result.warnings.extend(self._warnings)
        return result

    def _load_config(self) -> dict[str, Any]:
        cfg_path = self._config_dir / "template.yaml"
        if cfg_path.exists():
            try:
                return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as e:
                self._warnings.append(f"Failed to load {cfg_path.name}: {e}")
        return {}

    def _build_package(self, entry: Any, config: dict[str, Any]) -> dict[str, Any]:
        name = entry.name or ""
        slug = name.lower().replace(" ", "_").replace(".", "")
        description = entry.description or ""
        steps = list(entry.steps or [])

        def _fmt_md(items: list[str], fallback: str = "No steps defined") -> str:
            return (
                "\n".join(f"{i + 1}. {s}" for i, s in enumerate(items))
                if items
                else fallback
            )

        steps_md = _fmt_md(steps)

        workflow_md = config.get("workflow_template", "").format(
            name=name,
            description=description,
            steps_md=steps_md,
        )

        return {
            "slug": slug,
            "name": name,
            "yaml": {
                "name": name,
                "description": description,
                "steps": steps,
            },
            "workflow_md": workflow_md,
        }

    def write_artifacts(self, result: Result, output_dir: Path) -> list[Path]:
        created: list[Path] = []

        for package in result.workflows:
            slug = package["slug"]
            wf_dir = output_dir / "workflows" / slug
            wf_dir.mkdir(parents=True, exist_ok=True)

            yaml_path = wf_dir / "workflow.yaml"
            yaml_path.write_text(
                yaml.dump(package["yaml"], default_flow_style=False, sort_keys=False),
                encoding="utf-8",
            )
            created.append(yaml_path)

            doc_path = wf_dir / "workflow.md"
            doc_path.write_text(package["workflow_md"], encoding="utf-8")
            created.append(doc_path)

        return created

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self._registry.workflows:
            errors.append("No workflows defined in registry")
        return errors
