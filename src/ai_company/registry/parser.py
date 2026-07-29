def parse_company_data(raw: dict) -> dict:
    name = raw.get("name", "")
    if not isinstance(name, str):
        name = str(name) if name else ""
    return {
        "name": name,
        "description": raw.get("description"),
        "company_name": raw.get("company_name"),
        "department_names": raw.get("departments", []),
    }


def parse_departments(raw: dict) -> dict[str, dict]:
    departments: dict[str, dict] = {}
    if not isinstance(raw, dict):
        return departments
    for dept_name, roles_list in raw.items():
        roles: list[dict] = []
        if isinstance(roles_list, list):
            for item in roles_list:
                if isinstance(item, dict):
                    for title, desc in item.items():
                        roles.append(
                            {"title": str(title), "description": str(desc) if desc else ""}
                        )
        departments[dept_name] = {"name": dept_name, "roles": roles}
    return departments


def parse_list_field(raw: dict, key: str, model_keys: list[str]) -> list[dict]:
    items = raw.get(key, [])
    if not isinstance(items, list):
        items = [items] if items else []
    result: list[dict] = []
    for item in items:
        if isinstance(item, dict):
            entry = {k: item.get(k) for k in model_keys}
            result.append(entry)
        elif isinstance(item, str):
            entry = {model_keys[0]: item}
            result.append(entry)
    return result


def parse_registry(raw_data: dict[str, dict]) -> dict:
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
        "executives": parse_list_field(raw_executives, "members", ["name", "title"]),
        "policies": parse_list_field(raw_policies, "items", ["name", "description"]),
        "specialists": parse_list_field(raw_specialists, "list", ["name", "expertise"]),
        "workflows": parse_list_field(raw_workflows, "items", ["name", "description", "steps"]),
    }
