"""Department Generator — produces per-department artifact packages.

Each department in the manifest gets:
  - ``department.yaml`` — structured configuration
  - ``README.md`` — human-readable department overview
  - ``prompt.md`` — department agent prompt

All output goes to ``generated/departments/{slug}/``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ai_company.generator.context import GeneratorContext
from ai_company.generator.prompt_generator import PromptGenerator
from ai_company.models.company import (
    CompanyManifest,
    CompanyRegistry,
    ManifestDepartment,
)

_DEFAULT_RESPONSIBILITIES: dict[str, list[str]] = {
    "engineering": [
        "Design, build, and maintain software systems",
        "Ensure code quality through review and testing",
        "Manage technical infrastructure and deployment pipelines",
        "Collaborate with product on roadmap delivery",
    ],
    "finance": [
        "Manage financial planning and budgeting",
        "Process accounts payable and receivable",
        "Prepare financial reports and forecasts",
        "Ensure regulatory and tax compliance",
    ],
    "operations": [
        "Optimize business processes and workflows",
        "Manage facilities and vendor relationships",
        "Coordinate cross-functional initiatives",
        "Track operational KPIs and reporting",
    ],
    "security": [
        "Implement and maintain security controls",
        "Conduct risk assessments and audits",
        "Respond to security incidents",
        "Develop security awareness training",
    ],
    "marketing": [
        "Develop brand strategy and positioning",
        "Create content and manage communications",
        "Drive demand generation and lead acquisition",
        "Manage events and community engagement",
    ],
    "sales": [
        "Manage enterprise and channel sales pipelines",
        "Develop and maintain customer relationships",
        "Negotiate contracts and close deals",
        "Track revenue targets and forecasting",
    ],
    "hr": [
        "Manage talent acquisition and onboarding",
        "Administer compensation and benefits",
        "Foster organizational culture and DEI",
        "Support employee development and relations",
    ],
    "legal": [
        "Manage corporate governance and compliance",
        "Oversee intellectual property and contracts",
        "Provide legal counsel to leadership",
        "Handle regulatory filings and disputes",
    ],
    "it": [
        "Maintain internal technology infrastructure",
        "Provide end-user support and device management",
        "Manage enterprise software and licenses",
        "Ensure business continuity and disaster recovery",
    ],
    "data": [
        "Build and maintain data pipelines",
        "Develop analytics and reporting platforms",
        "Ensure data quality and governance",
        "Enable self-service analytics across teams",
    ],
    "ai": [
        "Research and develop AI/ML models",
        "Build and maintain agent systems",
        "Evaluate model performance and safety",
        "Collaborate on AI product roadmap",
    ],
    "research": [
        "Conduct applied and fundamental research",
        "Publish findings and contribute to open source",
        "Explore emerging technologies and trends",
        "Collaborate with product for technology transfer",
    ],
    "product": [
        "Define product vision and strategy",
        "Manage product roadmap and prioritisation",
        "Drive product discovery and user research",
        "Coordinate cross-functional delivery",
    ],
    "customer-success": [
        "Manage customer onboarding and adoption",
        "Drive retention and expansion revenue",
        "Gather feedback and advocate for customers",
        "Build customer community and knowledge base",
    ],
}

_DEFAULT_DEPENDENCIES: dict[str, list[str]] = {
    "engineering": [
        "Works with Product on feature definition and prioritisation",
        "Depends on Data for analytics infrastructure",
        "Collaborates with Security on secure coding practices",
        "Works with AI on model integration",
    ],
    "finance": [
        "Supports all departments with budget planning",
        "Reports financial performance to Executive",
        "Works with Operations on procurement",
    ],
    "marketing": [
        "Collaborates with Sales on lead generation",
        "Works with Product on go-to-market strategy",
        "Coordinates with Design on brand assets",
    ],
    "sales": [
        "Works with Marketing on pipeline generation",
        "Coordinates with Legal on contract terms",
        "Reports revenue forecasts to Finance",
    ],
    "ai": [
        "Collaborates with Engineering on model deployment",
        "Works with Research on novel architectures",
        "Supports Product with AI feature roadmap",
    ],
    "product": [
        "Works with Engineering on delivery",
        "Partners with Marketing on launches",
        "Collaborates with Sales on customer needs",
    ],
}


class DepartmentGenerator:
    """Generate per-department artifact packages from manifest and registry.

    Usage::

        gen = DepartmentGenerator(registry, manifest)
        result = gen.generate()
        gen.write_artifacts(result, output_dir)
    """

    def __init__(
        self,
        registry: CompanyRegistry,
        manifest: CompanyManifest | None = None,
        config_dir: str | Path = Path("config/departments"),
    ) -> None:
        self._registry = registry
        self._manifest = manifest or self._build_minimal_manifest()
        self._config_dir = Path(config_dir)
        self._warnings: list[str] = []

    class Result:
        """Container for all generated department artifacts."""

        def __init__(self) -> None:
            self.departments: list[dict[str, Any]] = []
            self.warnings: list[str] = []

        def summary(self) -> dict[str, Any]:
            return {
                "departments": len(self.departments),
                "warnings": len(self.warnings),
            }

    def generate(self) -> Result:
        """Generate artifact data for every department in the manifest."""
        result = self.Result()

        config = self._load_config()

        for dept in self._manifest.departments:
            if not dept.name:
                continue
            package = self._build_package(dept, config)
            result.departments.append(package)

        result.warnings.extend(self._warnings)
        return result

    def _load_config(self) -> dict[str, Any]:
        """Load config/departments/template.yaml."""
        cfg_path = self._config_dir / "template.yaml"
        if cfg_path.exists():
            try:
                return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as e:
                self._warnings.append(f"Failed to load {cfg_path.name}: {e}")
        return {}

    def _build_package(
        self, dept: ManifestDepartment, config: dict[str, Any]
    ) -> dict[str, Any]:
        slug = dept.name.lower().replace(" ", "-").replace("_", "-")
        name_lower = dept.name.lower()

        # Roles from registry
        reg_dept = self._registry.departments.get(name_lower)
        roles = reg_dept.roles if reg_dept else []

        def _fmt_md(items: list[str], fallback: str = "None defined") -> str:
            return "\n".join(f"- {i}" for i in items) if items else fallback

        roles_md = _fmt_md(
            [
                f"**{r.title}** — {r.description}"
                if r.description
                else f"**{r.title}**"
                for r in roles
            ],
            "No roles defined",
        )

        agents_md = _fmt_md(
            [
                f"**{r.title}** Agent — {r.description}"
                if r.description
                else f"**{r.title}** Agent"
                for r in roles
            ],
            "No agents defined",
        )

        # Prompt via PromptGenerator
        ctx = GeneratorContext(self._manifest, self._registry)
        prompt_gen = PromptGenerator(ctx)
        prompt_md = prompt_gen.generate_department_prompt(dept.name)

        readme = config.get("readme_template", "").format(
            display_name=dept.display_name or dept.name.title(),
            description=dept.description or "",
            roles_md=roles_md,
        )

        agents_md_content = config.get("agents_template", "").format(
            display_name=dept.display_name or dept.name.title(),
            agents_md=agents_md,
        )

        return {
            "slug": slug,
            "name": dept.name,
            "display_name": dept.display_name or dept.name.title(),
            "description": dept.description or "",
            "yaml": {
                "name": dept.name,
                "display_name": dept.display_name or dept.name.title(),
                "description": dept.description or "",
                "roles": [
                    {"title": r.title, "description": r.description} for r in roles
                ],
            },
            "readme_md": readme,
            "prompt_md": prompt_md,
            "agents_md": agents_md_content,
        }

    def write_artifacts(self, result: Result, output_dir: Path) -> list[Path]:
        """Write all department artifact packages to ``output_dir/departments/{slug}/``.

        Returns a list of created file paths.
        """
        created: list[Path] = []

        for package in result.departments:
            slug = package["slug"]
            dept_dir = output_dir / "departments" / slug
            dept_dir.mkdir(parents=True, exist_ok=True)

            yaml_path = dept_dir / "department.yaml"
            yaml_path.write_text(
                yaml.dump(package["yaml"], default_flow_style=False, sort_keys=False),
                encoding="utf-8",
            )
            created.append(yaml_path)

            readme_path = dept_dir / "README.md"
            readme_path.write_text(package["readme_md"], encoding="utf-8")
            created.append(readme_path)

            prompt_path = dept_dir / "prompt.md"
            prompt_path.write_text(package["prompt_md"], encoding="utf-8")
            created.append(prompt_path)

            agents_path = dept_dir / "agents.md"
            agents_path.write_text(package["agents_md"], encoding="utf-8")
            created.append(agents_path)

        return created

    def validate(self) -> list[str]:
        """Validate that the manifest has departments defined."""
        errors: list[str] = []
        if not self._manifest.departments:
            errors.append("No departments defined in manifest")
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
