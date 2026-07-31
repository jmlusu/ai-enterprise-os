from pathlib import Path
from typing import Any

from ai_company.models.company import CompanyManifest, CompanyRegistry


class GeneratorContext:
    """Unified context holding CompanyManifest + CompanyRegistry + settings + paths.

    Provides a single ``to_dict()`` method that merges manifest data,
    registry data, and runtime settings into a flat dict suitable for
    passing to :class:`~ai_company.template_engine.renderer.Renderer`.
    """

    def __init__(
        self,
        manifest: CompanyManifest,
        registry: CompanyRegistry,
        *,
        company_dir: Path = Path("company"),
        templates_dir: Path = Path("templates"),
        output_dir: Path = Path("generated"),
        config_dir: Path = Path("config/company"),
        settings: dict[str, Any] | None = None,
    ) -> None:
        self.manifest = manifest
        self.registry = registry
        self.company_dir = company_dir
        self.templates_dir = templates_dir
        self.output_dir = output_dir
        self.config_dir = config_dir
        self._settings = dict(settings or {})

    @property
    def settings(self) -> dict[str, Any]:
        return dict(self._settings)

    def get(self, key: str, default: Any = None) -> Any:
        parts = key.split(".")
        val: Any = self.to_dict()
        for part in parts:
            if isinstance(val, dict):
                val = val.get(part, default)
            else:
                return default
        return val

    def to_dict(self) -> dict[str, Any]:
        normalized = self.manifest.normalize()
        reg = self.registry

        departments_list = []
        for d in normalized.departments:
            dept_data = reg.departments.get(d.name)
            departments_list.append(
                {
                    "name": d.name,
                    "display_name": d.display_name or d.name.title(),
                    "description": d.description or "",
                    "roles": [
                        {"title": r.title, "description": r.description}
                        for r in (dept_data.roles if dept_data else [])
                    ],
                    "role_count": len(dept_data.roles) if dept_data else 0,
                }
            )

        def _entries_to_dicts(
            entries: list[Any], keys: list[str]
        ) -> list[dict[str, Any]]:
            result = []
            for e in entries:
                d = {}
                for k in keys:
                    v = getattr(e, k, None)
                    if v is not None:
                        d[k] = v
                result.append(d)
            return result

        return {
            "company": {
                "name": normalized.name,
                "company_name": normalized.company_name or "",
                "description": normalized.description or "",
                "version": normalized.version or "",
                "department_count": len(normalized.departments),
                "departments": departments_list,
                "vision": {
                    "name": normalized.name,
                    "company_name": normalized.company_name or "",
                    "description": normalized.description or "",
                },
                "board": _entries_to_dicts(reg.board, ["name", "role"]),
                "executives": _entries_to_dicts(
                    reg.executives,
                    [
                        "name",
                        "title",
                        "bio",
                        "department",
                        "responsibilities",
                        "kpis",
                        "budget_authority",
                        "direct_reports",
                        "reports_to",
                        "status",
                        "start_date",
                        "email",
                    ],
                ),
                "executive_agents": _entries_to_dicts(
                    reg.executive_agents,
                    ["name", "role", "model", "instructions", "tools", "department"],
                ),
                "specialists": _entries_to_dicts(
                    reg.specialists,
                    ["name", "expertise", "department", "bio", "tools"],
                ),
                "policies": _entries_to_dicts(reg.policies, ["name", "description"]),
                "workflows": _entries_to_dicts(
                    reg.workflows, ["name", "description", "steps"]
                ),
                "board_members": _entries_to_dicts(
                    reg.board_members,
                    [
                        "name",
                        "role",
                        "term_start",
                        "term_end",
                        "committees",
                        "independent",
                    ],
                ),
                "committees": _entries_to_dicts(
                    reg.committees,
                    ["name", "purpose", "chair", "members", "meeting_frequency"],
                ),
                "meetings": _entries_to_dicts(
                    reg.meetings,
                    [
                        "title",
                        "meeting_date",
                        "meeting_type",
                        "attendees",
                        "minutes",
                        "action_items",
                    ],
                ),
                "voting_records": _entries_to_dicts(
                    reg.voting_records,
                    [
                        "motion",
                        "proposed_by",
                        "votes_for",
                        "votes_against",
                        "passed",
                        "vote_date",
                    ],
                ),
                "agents": _entries_to_dicts(
                    reg.agents,
                    ["name", "role", "model", "instructions", "tools", "department"],
                ),
                "policy_documents": _entries_to_dicts(
                    reg.policy_documents,
                    ["name", "description", "scope", "version", "owner", "rules"],
                ),
                "budgets": _entries_to_dicts(
                    reg.budgets,
                    [
                        "department",
                        "fiscal_year",
                        "total",
                        "spent",
                        "currency",
                        "categories",
                    ],
                ),
                "kpis": _entries_to_dicts(
                    reg.kpis,
                    [
                        "name",
                        "target",
                        "current",
                        "unit",
                        "owner",
                        "frequency",
                        "trend",
                    ],
                ),
                "risks": _entries_to_dicts(
                    reg.risks,
                    [
                        "description",
                        "impact",
                        "likelihood",
                        "mitigation",
                        "owner",
                        "status",
                    ],
                ),
                "decisions": _entries_to_dicts(
                    reg.decisions,
                    [
                        "title",
                        "decision_date",
                        "author",
                        "rationale",
                        "outcome",
                        "stakeholders",
                    ],
                ),
                "permissions": _entries_to_dicts(
                    reg.permissions,
                    ["resource", "role", "actions", "constraints"],
                ),
                "integrations": _entries_to_dicts(
                    reg.integrations,
                    ["name", "type", "version", "status"],
                ),
                "tools": _entries_to_dicts(
                    reg.tools,
                    ["name", "purpose", "category", "access_roles"],
                ),
                "governance": {
                    "framework": reg.governance.framework,
                    "policies": reg.governance.policies,
                    "controls": reg.governance.controls,
                    "compliance_standards": reg.governance.compliance_standards,
                    "review_cycle": reg.governance.review_cycle,
                },
                "strategy": {
                    "name": reg.strategy.name,
                    "description": reg.strategy.description,
                    "objectives": reg.strategy.objectives,
                    "metrics": reg.strategy.metrics,
                    "timeline": reg.strategy.timeline,
                    "owner": reg.strategy.owner,
                    "status": reg.strategy.status,
                },
                "culture": {
                    "values": reg.culture.values,
                    "behaviors": reg.culture.behaviors,
                    "norms": reg.culture.norms,
                    "rituals": reg.culture.rituals,
                },
            },
            "settings": dict(self._settings),
        }
