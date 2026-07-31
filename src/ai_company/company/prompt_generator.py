"""Prompt Library Generator — consolidates agent prompts for all entities.

Generates a prompt library containing prompts for executives, departments,
and specialists into ``generated/prompts/``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_company.generator.context import GeneratorContext
from ai_company.generator.prompt_generator import PromptGenerator as PromptGen
from ai_company.models.company import CompanyManifest, CompanyRegistry


class PromptLibraryGenerator:
    """Generate a consolidated prompt library from registry data."""

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
            self.prompts: list[dict[str, Any]] = []
            self.warnings: list[str] = []

        def summary(self) -> dict[str, Any]:
            return {
                "prompts": len(self.prompts),
                "warnings": len(self.warnings),
            }

    def generate(self) -> Result:
        result = self.Result()
        ctx = GeneratorContext(self._manifest, self._registry)
        prompt_gen = PromptGen(ctx)

        for ex in self._registry.executives:
            if not ex.name:
                continue
            prompt_text = prompt_gen.generate_executive_prompt(ex.name)
            result.prompts.append(
                {
                    "slug": ex.name.lower().replace(" ", "_").replace(".", ""),
                    "type": "executive",
                    "name": ex.name,
                    "prompt_text": prompt_text,
                }
            )

        for name in self._registry.departments:
            prompt_text = prompt_gen.generate_department_prompt(name)
            result.prompts.append(
                {
                    "slug": name.lower().replace(" ", "_").replace(".", ""),
                    "type": "department",
                    "name": name,
                    "prompt_text": prompt_text,
                }
            )

        for spec in self._registry.specialists:
            if not spec.name:
                continue
            prompt_text = prompt_gen.generate_specialist_prompt(spec.name)
            result.prompts.append(
                {
                    "slug": spec.name.lower().replace(" ", "_").replace(".", ""),
                    "type": "specialist",
                    "name": spec.name,
                    "prompt_text": prompt_text,
                }
            )

        result.warnings.extend(self._warnings)
        return result

    def write_artifacts(self, result: Result, output_dir: Path) -> list[Path]:
        created: list[Path] = []
        prompts_dir = output_dir / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)

        for entry in result.prompts:
            filename = f"{entry['type']}__{entry['slug']}.md"
            path = prompts_dir / filename
            path.write_text(entry["prompt_text"], encoding="utf-8")
            created.append(path)

        # Write index
        index_lines = ["# Prompt Library\n", f"Total prompts: {len(result.prompts)}\n"]
        for entry in result.prompts:
            index_lines.append(
                f"- [{entry['type']}] {entry['name']} -> {entry['type']}__{entry['slug']}.md"
            )
        index_path = prompts_dir / "INDEX.md"
        index_path.write_text("\n".join(index_lines), encoding="utf-8")
        created.append(index_path)

        return created

    def validate(self) -> list[str]:
        errors: list[str] = []
        if (
            not self._registry.executives
            and not self._registry.departments
            and not self._registry.specialists
        ):
            errors.append("No entities found to generate prompts for")
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
