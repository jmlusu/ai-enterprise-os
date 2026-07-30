"""Executive Generator — produces per-executive artifact packages.

Each executive in the registry gets:
  - ``executive.yaml`` — structured configuration
  - ``prompt.md`` — agent prompt (via PromptGenerator)
  - ``profile.md`` — human-readable Markdown profile
  - ``knowledge.md`` — domain expertise and relationship knowledge base
  - ``memory.md`` — memory structure for session persistence
  - ``agent.py`` — Python agent wrapper class

All output goes to ``generated/executives/{slug}/``.
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
    ExecutiveEntry,
)

_DEFAULT_DOMAIN_EXPERTISE: dict[str, list[str]] = {
    "chief executive officer": [
        "Strategic leadership and vision setting",
        "Corporate governance and board relations",
        "Capital allocation and M&A",
        "Organizational culture and talent",
        "Stakeholder communication and investor relations",
    ],
    "chief technology officer": [
        "Software architecture and distributed systems",
        "AI/ML platform infrastructure",
        "Developer experience and platform engineering",
        "R&D portfolio management",
        "Open-source strategy and community",
    ],
    "chief financial officer": [
        "Financial planning and analysis (FP&A)",
        "Fundraising and capital markets",
        "SaaS metrics and unit economics",
        "Risk management and compliance",
        "Revenue operations and billing systems",
    ],
    "chief operating officer": [
        "Operational excellence and process optimization",
        "Cross-functional execution and program management",
        "Scale operations and infrastructure",
        "People operations and organizational design",
        "Facilities and distributed workforce management",
    ],
    "chief marketing officer": [
        "Brand strategy and positioning",
        "Developer marketing and community building",
        "Content marketing and thought leadership",
        "Demand generation and growth marketing",
        "Product marketing and go-to-market strategy",
    ],
    "chief ai officer": [
        "Large language models and agent systems",
        "AI safety and alignment research",
        "Model evaluation and benchmarking",
        "AI ethics and responsible AI deployment",
        "Research publishing and IP strategy",
    ],
    "chief human resources officer": [
        "Talent acquisition and employer branding",
        "Organizational design and effectiveness",
        "DEI strategy and programs",
        "Learning and development",
        "Compensation and benefits strategy",
    ],
    "chief legal officer": [
        "AI regulation and compliance",
        "Intellectual property management",
        "Corporate governance and board advisory",
        "Contract negotiation and risk management",
        "Privacy and data protection",
    ],
    "chief information security officer": [
        "Zero-trust architecture and implementation",
        "Incident response and forensics",
        "AI model security and red-teaming",
        "Security awareness and training",
        "Vulnerability management and penetration testing",
    ],
}

_RELATIONSHIP_TEMPLATES: dict[str, list[str]] = {
    "chief executive officer": [
        "Reports to the Board of Directors (fiduciary duty)",
        "Works with CFO on capital allocation and financial strategy",
        "Works with CTO on technology vision and R&D investment",
        "Works with CMO on brand, positioning, and market strategy",
        "Leads the executive team through direct reports and skip-level engagement",
    ],
    "chief technology officer": [
        "Reports to the CEO on technology vision and execution",
        "Collaborates with CAIO on AI research and model architecture",
        "Collaborates with CISO on security architecture and infrastructure",
        "Works with product department on technical roadmap",
        "Leads engineering department through engineering managers",
    ],
}


class ExecutiveGenerator:
    """Generate per-executive artifact packages from registry data.

    Usage::

        gen = ExecutiveGenerator(registry, manifest)
        result = gen.generate()
        gen.write_artifacts(result, output_dir)
    """

    def __init__(
        self,
        registry: CompanyRegistry,
        manifest: CompanyManifest | None = None,
        config_dir: str | Path = Path("config/executives"),
    ) -> None:
        self._registry = registry
        self._manifest = manifest or self._build_minimal_manifest()
        self._config_dir = Path(config_dir)
        self._warnings: list[str] = []

    # ------------------------------------------------------------------
    # Result container
    # ------------------------------------------------------------------

    class Result:
        """Container for all generated executive artifacts."""

        def __init__(self) -> None:
            self.executables: list[dict[str, Any]] = []
            self.warnings: list[str] = []

        def summary(self) -> dict[str, Any]:
            return {
                "executives": len(self.executables),
                "warnings": len(self.warnings),
            }

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def generate(self) -> Result:
        """Generate artifact data for every executive in the registry."""
        result = self.Result()

        config = self._load_config()

        for exec_entry in self._registry.executives:
            if not exec_entry.name:
                continue
            package = self._build_package(exec_entry, config)
            result.executables.append(package)

        result.warnings.extend(self._warnings)
        return result

    def _load_config(self) -> dict[str, Any]:
        """Load config/executives/template.yaml."""
        cfg_path = self._config_dir / "template.yaml"
        if cfg_path.exists():
            try:
                return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as e:
                self._warnings.append(f"Failed to load {cfg_path.name}: {e}")
        return {}

    # ------------------------------------------------------------------
    # Package builder
    # ------------------------------------------------------------------

    def _build_package(
        self, entry: ExecutiveEntry, config: dict[str, Any]
    ) -> dict[str, Any]:
        name = entry.name or ""
        slug = name.lower().replace(" ", "_").replace(".", "")
        title_lower = (entry.title or "").lower()
        ac = entry.agent_config

        # Generate prompt via PromptGenerator
        ctx = GeneratorContext(self._manifest, self._registry)
        prompt_gen = PromptGenerator(ctx)
        prompt_text = prompt_gen.generate_executive_prompt(name)

        # Knowledge base
        default_domain = _DEFAULT_DOMAIN_EXPERTISE.get(title_lower, [])
        relationships = _RELATIONSHIP_TEMPLATES.get(title_lower, [])
        if not relationships:
            relationships = [
                f"Reports to {entry.reports_to or 'Board of Directors'}",
            ]

        # Format helpers
        def _fmt_md(items: list[str], fallback: str = "None defined") -> str:
            return "\n".join(f"- {i}" for i in items) if items else fallback

        domain_md = _fmt_md(default_domain)
        relationships_md = _fmt_md(relationships)
        responsibilities_md = _fmt_md(entry.responsibilities)
        kpis_md = _fmt_md(
            [f"**{k}** — tracked and reported" for k in (entry.kpis or [])],
            "No KPIs assigned",
        )
        direct_reports_md = _fmt_md(entry.direct_reports, "No direct reports")
        budget_md = (
            f"Budget Authority: ${entry.budget_authority:,.0f}"
            if entry.budget_authority > 0
            else "No budget data"
        )
        dept_scope_md = _fmt_md(ac.department_scope)

        culture_vals = self._registry.culture.values or []
        culture_md = _fmt_md(culture_vals, "No culture values defined")
        strategy_context = self._registry.strategy.description or "No active strategy"

        # Agent.py values
        python_class_name = "".join(word for word in name.replace(".", "").split())

        profile = config.get("profile_template", "").format(
            name=entry.name,
            title=entry.title or "Executive",
            department=entry.department or "General",
            status=entry.status or "active",
            reports_to=entry.reports_to or "Board of Directors",
            start_date=entry.start_date or "Unknown",
            email=entry.email or "N/A",
            bio=entry.bio or "No biography available.",
            responsibilities_md=responsibilities_md,
            kpis_md=kpis_md,
            budget_md=budget_md,
            direct_reports_md=direct_reports_md,
        )

        knowledge = config.get("knowledge_template", "").format(
            name=entry.name,
            title=entry.title or "Executive",
            domain_expertise=domain_md,
            relationships_md=relationships_md,
            budget_authority=f"${entry.budget_authority:,.0f}"
            if entry.budget_authority > 0
            else "None",
            department_scope_md=dept_scope_md,
            reports_to=entry.reports_to or "Board of Directors",
            strategy_context=strategy_context,
            culture_md=culture_md,
        )

        memory = config.get("memory_template", "").format(
            name=entry.name,
            title=entry.title or "Executive",
            company=self._manifest.company_name or self._manifest.name,
            start_date=entry.start_date or "Unknown",
            status=entry.status or "active",
        )

        agent_py = config.get("agent_py_template", "").format(
            name=entry.name,
            title=entry.title or "Executive",
            python_class_name=python_class_name,
            config_dir=f"generated/executives/{slug}",
            agent_model=ac.model,
            agent_temperature=ac.temperature,
            agent_tools_list=list(ac.tools),
        )

        return {
            "slug": slug,
            "name": entry.name,
            "title": entry.title or "Executive",
            "yaml": self._to_yaml_dict(entry),
            "prompt_md": prompt_text,
            "profile_md": profile,
            "knowledge_md": knowledge,
            "memory_md": memory,
            "agent_py": agent_py,
        }

    # ------------------------------------------------------------------
    # YAML serialization
    # ------------------------------------------------------------------

    @staticmethod
    def _to_yaml_dict(entry: ExecutiveEntry) -> dict[str, Any]:
        return {
            "name": entry.name,
            "title": entry.title,
            "bio": entry.bio,
            "department": entry.department,
            "responsibilities": list(entry.responsibilities),
            "kpis": list(entry.kpis),
            "budget_authority": entry.budget_authority,
            "direct_reports": list(entry.direct_reports),
            "reports_to": entry.reports_to,
            "status": entry.status,
            "start_date": entry.start_date,
            "email": entry.email,
            "agent_config": {
                "model": entry.agent_config.model,
                "instructions": entry.agent_config.instructions,
                "tools": list(entry.agent_config.tools),
                "temperature": entry.agent_config.temperature,
                "department_scope": list(entry.agent_config.department_scope),
            },
        }

    # ------------------------------------------------------------------
    # Artifact writers
    # ------------------------------------------------------------------

    def write_artifacts(self, result: Result, output_dir: Path) -> list[Path]:
        """Write all executive artifact packages to ``output_dir/executives/{slug}/``.

        Returns a list of created file paths.
        """
        created: list[Path] = []

        for package in result.executables:
            slug = package["slug"]
            exec_dir = output_dir / "executives" / slug
            exec_dir.mkdir(parents=True, exist_ok=True)

            # executive.yaml
            yaml_path = exec_dir / "executive.yaml"
            yaml_path.write_text(
                yaml.dump(package["yaml"], default_flow_style=False, sort_keys=False),
                encoding="utf-8",
            )
            created.append(yaml_path)

            # prompt.md
            prompt_path = exec_dir / "prompt.md"
            prompt_path.write_text(package["prompt_md"], encoding="utf-8")
            created.append(prompt_path)

            # profile.md
            profile_path = exec_dir / "profile.md"
            profile_path.write_text(package["profile_md"], encoding="utf-8")
            created.append(profile_path)

            # knowledge.md
            knowledge_path = exec_dir / "knowledge.md"
            knowledge_path.write_text(package["knowledge_md"], encoding="utf-8")
            created.append(knowledge_path)

            # memory.md
            memory_path = exec_dir / "memory.md"
            memory_path.write_text(package["memory_md"], encoding="utf-8")
            created.append(memory_path)

            # agent.py
            agent_path = exec_dir / "agent.py"
            agent_path.write_text(package["agent_py"], encoding="utf-8")
            created.append(agent_path)

        return created

    # ------------------------------------------------------------------
    # Manifest helper
    # ------------------------------------------------------------------

    def _build_minimal_manifest(self) -> CompanyManifest:
        return CompanyManifest(
            name=self._registry.vision.company_name
            or self._registry.vision.name
            or "Company",
            company_name=self._registry.vision.company_name
            or self._registry.vision.name,
            description=self._registry.vision.description or "",
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self._registry.executives:
            errors.append("No executives defined in registry")
        return errors
