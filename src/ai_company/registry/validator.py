from typing import Any

from pydantic import ValidationError

from ai_company.models.company import (
    BoardEntry,
    DepartmentData,
    ExecutiveEntry,
    PolicyEntry,
    Role,
    SpecialistEntry,
    VisionData,
    WorkflowEntry,
)


def validate_parsed_data(parsed: dict[str, Any]) -> Any:
    from ai_company.validator.reports import ValidationReport

    report: ValidationReport = ValidationReport(target="parsed_data", passed=True)

    vision_raw = parsed.get("vision", {})
    try:
        VisionData(**vision_raw)
    except ValidationError as e:
        report.add_error(f"vision: {e}")

    departments_raw = parsed.get("departments", {})
    if not isinstance(departments_raw, dict):
        report.add_error("departments: must be a mapping of department names to definitions")
    else:
        for dept_name, dept_raw in departments_raw.items():
            if isinstance(dept_raw, dict):
                roles_raw = dept_raw.get("roles", [])
                roles: list[Role] = []
                for r in roles_raw:
                    try:
                        roles.append(Role(**r))
                    except ValidationError as e:
                        report.add_error(f"departments.{dept_name}.role: {e}")
                try:
                    DepartmentData(name=dept_name, roles=roles)
                except ValidationError as e:
                    report.add_error(f"departments.{dept_name}: {e}")
            else:
                report.add_error(f"departments.{dept_name}: expected a mapping")

    list_fields = {
        "board": (BoardEntry, parsed.get("board", [])),
        "executives": (ExecutiveEntry, parsed.get("executives", [])),
        "policies": (PolicyEntry, parsed.get("policies", [])),
        "specialists": (SpecialistEntry, parsed.get("specialists", [])),
        "workflows": (WorkflowEntry, parsed.get("workflows", [])),
    }

    for field_name, (model_cls, items) in list_fields.items():
        if not isinstance(items, list):
            report.add_error(f"{field_name}: expected a list")
            continue
        for idx, item in enumerate(items):
            if isinstance(item, dict):
                try:
                    model_cls(**item)
                except ValidationError as e:
                    report.add_error(f"{field_name}[{idx}]: {e}")

    dept_names = parsed.get("department_names", [])
    if not isinstance(dept_names, list):
        report.add_warning("department_names: expected a list")
    elif len(dept_names) < 1:
        report.add_warning("company: no departments defined")

    return report
