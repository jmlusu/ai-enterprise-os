"""Specialist Generator — produces per-specialist artifact packages.

Each specialist in the registry gets:
  - ``specialist.yaml`` — structured configuration
  - ``prompt.md`` — agent prompt (via PromptGenerator)
  - ``profile.md`` — human-readable Markdown profile
  - ``memory.md`` — memory structure for session persistence

All output goes to ``generated/specialists/{slug}/``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ai_company.generator.context import GeneratorContext
from ai_company.generator.prompt_generator import PromptGenerator
from ai_company.models.company import CompanyManifest, CompanyRegistry


class SpecialistGenerator:
    """Generate per-specialist artifact packages from registry data."""

    def __init__(
        self,
        registry: CompanyRegistry,
        manifest: CompanyManifest | None = None,
        config_dir: str | Path = Path("config/specialists"),
    ) -> None:
        self._registry = registry
        self._manifest = manifest or self._build_minimal_manifest()
        self._config_dir = Path(config_dir)
        self._warnings: list[str] = []

    class Result:
        """Container for all generated specialist artifacts."""

        def __init__(self) -> None:
            self.specialists: list[dict[str, Any]] = []
            self.warnings: list[str] = []

        def summary(self) -> dict[str, Any]:
            return {
                "specialists": len(self.specialists),
                "warnings": len(self.warnings),
            }

    def generate(self) -> Result:
        """Generate artifact data for every specialist in the registry."""
        result = self.Result()
        config = self._load_config()

        for entry in self._registry.specialists:
            if not entry.name:
                continue
            package = self._build_package(entry, config)
            result.specialists.append(package)

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
        expertise = entry.expertise or "General"

        ctx = GeneratorContext(self._manifest, self._registry)
        prompt_gen = PromptGenerator(ctx)
        prompt_text = prompt_gen.generate_specialist_prompt(name)

        bio = getattr(entry, "bio", "") or f"{expertise} specialist."

        profile = config.get("profile_template", "").format(
            name=name,
            expertise=expertise,
            bio=bio,
            prompt_text=prompt_text,
        )

        memory = config.get("memory_template", "").format(
            name=name,
            expertise=expertise,
            company=self._manifest.company_name or self._manifest.name,
        )

        return {
            "slug": slug,
            "name": name,
            "expertise": expertise,
            "yaml": {
                "name": name,
                "expertise": expertise,
            },
            "prompt_md": prompt_text,
            "profile_md": profile,
            "memory_md": memory,
        }

    def write_artifacts(self, result: Result, output_dir: Path) -> list[Path]:
        created: list[Path] = []

        for package in result.specialists:
            slug = package["slug"]
            spec_dir = output_dir / "specialists" / slug
            spec_dir.mkdir(parents=True, exist_ok=True)

            yaml_path = spec_dir / "specialist.yaml"
            yaml_path.write_text(
                yaml.dump(package["yaml"], default_flow_style=False, sort_keys=False),
                encoding="utf-8",
            )
            created.append(yaml_path)

            prompt_path = spec_dir / "prompt.md"
            prompt_path.write_text(package["prompt_md"], encoding="utf-8")
            created.append(prompt_path)

            profile_path = spec_dir / "profile.md"
            profile_path.write_text(package["profile_md"], encoding="utf-8")
            created.append(profile_path)

            memory_path = spec_dir / "memory.md"
            memory_path.write_text(package["memory_md"], encoding="utf-8")
            created.append(memory_path)

        return created

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self._registry.specialists:
            errors.append("No specialists defined in registry")
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
