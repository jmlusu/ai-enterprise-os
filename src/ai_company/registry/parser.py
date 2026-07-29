from typing import Any


def parse_company_data(raw: dict[str, Any]) -> dict[str, Any]:
    name = raw.get("name", "")
    if not isinstance(name, str):
        name = str(name) if name else ""
    return {
        "name": name,
        "description": raw.get("description"),
        "company_name": raw.get("company_name"),
        "department_names": raw.get("departments", []),
    }


def parse_departments(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    departments: dict[str, dict[str, Any]] = {}
    if not isinstance(raw, dict):
        return departments
    for dept_name, roles_list in raw.items():
        roles: list[dict[str, str]] = []
        if isinstance(roles_list, list):
            for item in roles_list:
                if isinstance(item, dict):
                    for title, desc in item.items():
                        roles.append(
                            {
                                "title": str(title),
                                "description": str(desc) if desc else "",
                            }
                        )
        departments[dept_name] = {"name": dept_name, "roles": roles}
    return departments


def parse_list_field(
    raw: dict[str, Any], key: str, model_keys: list[str]
) -> list[dict[str, Any]]:
    items = raw.get(key, [])
    if not isinstance(items, list):
        items = [items] if items else []
    result: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            entry = {k: item.get(k) for k in model_keys}
            result.append(entry)
        elif isinstance(item, str):
            entry = {model_keys[0]: item}
            result.append(entry)
    return result


def _parse_executives(members: list[Any]) -> list[dict[str, Any]]:
    """Parse executive members with rich fields and embedded agent_config."""
    result: list[dict[str, Any]] = []
    for item in members:
        if not isinstance(item, dict):
            continue
        entry: dict[str, Any] = {
            "name": item.get("name"),
            "title": item.get("title"),
            "bio": item.get("bio", ""),
            "department": item.get("department", ""),
            "responsibilities": item.get("responsibilities", []),
            "kpis": item.get("kpis", []),
            "budget_authority": item.get("budget_authority", 0.0),
            "direct_reports": item.get("direct_reports", []),
            "reports_to": item.get("reports_to", ""),
            "status": item.get("status", "active"),
            "start_date": item.get("start_date", ""),
            "email": item.get("email", ""),
        }
        # Extract nested agent_config
        raw_agent = item.get("agent_config", {}) or {}
        entry["agent_config"] = {
            "model": raw_agent.get("model", "gpt-4o"),
            "instructions": raw_agent.get("instructions", ""),
            "tools": raw_agent.get(
                "tools", ["registry-read", "kpi-dashboard", "budget-view"]
            ),
            "temperature": raw_agent.get("temperature", 0.0),
            "department_scope": raw_agent.get("department_scope", []),
        }
        result.append(entry)
    return result


def parse_registry(raw_data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    raw_company = raw_data.get("company", {}) or {}
    raw_departments = raw_data.get("departments", {}) or {}
    raw_board = raw_data.get("board", {}) or {}
    raw_executives = raw_data.get("executives", {}) or {}
    raw_policies = raw_data.get("policies", {}) or {}
    raw_specialists = raw_data.get("specialists", {}) or {}
    raw_workflows = raw_data.get("workflows", {}) or {}

    company = parse_company_data(raw_company)
    departments = parse_departments(raw_departments)

    return {
        "vision": {
            "name": company["name"],
            "description": company.get("description"),
            "company_name": company.get("company_name"),
        },
        "department_names": company.get("department_names", []),
        "departments": departments,
        "board": parse_list_field(raw_board, "members", ["name", "role"]),
        "executives": _parse_executives(raw_executives.get("members", [])),
        "policies": parse_list_field(raw_policies, "items", ["name", "description"]),
        "specialists": parse_list_field(raw_specialists, "list", ["name", "expertise"]),
        "workflows": parse_list_field(
            raw_workflows, "items", ["name", "description", "steps"]
        ),
    }


def parse_config_registry(config_data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Parse extended configuration data into structured dicts for the new models."""
    result: dict[str, Any] = {}

    raw_strategy = config_data.get("strategy", {}) or {}
    result["strategy"] = {
        "name": raw_strategy.get("name", ""),
        "description": raw_strategy.get("description", ""),
        "objectives": raw_strategy.get("objectives", []),
        "metrics": raw_strategy.get("metrics", []),
        "timeline": raw_strategy.get("timeline", ""),
        "owner": raw_strategy.get("owner", ""),
        "status": raw_strategy.get("status", "draft"),
    }

    raw_culture = config_data.get("culture", {}) or {}
    result["culture"] = {
        "values": raw_culture.get("values", []),
        "behaviors": raw_culture.get("behaviors", []),
        "norms": raw_culture.get("norms", []),
        "rituals": raw_culture.get("rituals", []),
    }

    raw_governance = config_data.get("governance", {}) or {}
    result["governance"] = {
        "framework": raw_governance.get("framework", "standard"),
        "policies": raw_governance.get("policies", []),
        "controls": raw_governance.get("controls", []),
        "compliance_standards": raw_governance.get("compliance_standards", []),
        "review_cycle": raw_governance.get("review_cycle", "quarterly"),
    }

    raw_policies = config_data.get("policies", {}) or {}
    policy_items = raw_policies.get("items", [])
    result["policy_documents"] = []
    for item in policy_items:
        if isinstance(item, dict):
            result["policy_documents"].append(
                {
                    "name": item.get("name", ""),
                    "description": item.get("description", ""),
                    "scope": item.get("scope", ""),
                    "version": item.get("version", "1.0.0"),
                    "effective_date": item.get("effective_date", ""),
                    "owner": item.get("owner", ""),
                    "rules": item.get("rules", []),
                }
            )

    raw_kpis = config_data.get("kpis", {}) or {}
    kpi_items = raw_kpis.get("kpis", [])
    result["kpis"] = []
    for item in kpi_items:
        if isinstance(item, dict):
            result["kpis"].append(
                {
                    "name": item.get("name", ""),
                    "target": item.get("target", 0),
                    "current": item.get("current", 0.0),
                    "unit": item.get("unit", ""),
                    "owner": item.get("owner", ""),
                    "frequency": item.get("frequency", "quarterly"),
                    "trend": item.get("trend", "flat"),
                }
            )

    raw_budget = config_data.get("budget", {}) or {}
    result["budgets"] = [
        {
            "department": "company",
            "fiscal_year": raw_budget.get("fiscal_year", ""),
            "total": raw_budget.get("total", 0.0),
            "spent": raw_budget.get("spent", 0.0),
            "currency": raw_budget.get("currency", "USD"),
            "categories": raw_budget.get("categories", {}),
        }
    ]
    raw_dept_budgets = raw_budget.get("departments", {})
    if isinstance(raw_dept_budgets, dict):
        for dept_name, dept_budget in raw_dept_budgets.items():
            if isinstance(dept_budget, dict):
                result["budgets"].append(
                    {
                        "department": dept_name,
                        "fiscal_year": raw_budget.get("fiscal_year", ""),
                        "total": dept_budget.get("total", 0.0),
                        "spent": dept_budget.get("spent", 0.0),
                        "currency": raw_budget.get("currency", "USD"),
                        "categories": dept_budget.get("categories", {}),
                    }
                )

    return result
