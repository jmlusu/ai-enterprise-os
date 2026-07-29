from typing import Any


class ResolutionReport:
    def __init__(
        self,
        resolved: dict[str, Any],
        unresolved_refs: list[str],
        warnings: list[str],
    ) -> None:
        self.resolved = resolved
        self.unresolved_refs = unresolved_refs
        self.warnings = warnings

    @property
    def success(self) -> bool:
        return len(self.unresolved_refs) == 0

    def merge_into(self, target: dict[str, Any]) -> dict[str, Any]:
        target["unresolved_refs"] = self.unresolved_refs
        return target


def resolve(
    parsed: dict[str, Any],
) -> ResolutionReport:
    unresolved: list[str] = []
    warnings: list[str] = []

    departments = dict(parsed.get("departments", {}))
    department_names = parsed.get("department_names", [])

    for dept_name in department_names:
        if dept_name not in departments:
            unresolved.append(dept_name)
            departments[dept_name] = {"name": dept_name, "roles": []}

    defined_in_yaml = set(departments.keys())
    referenced = set(department_names)
    extra = defined_in_yaml - referenced
    for name in sorted(extra):
        warnings.append(f"department '{name}' is defined but not listed in company.yaml")

    resolved = dict(parsed)
    resolved["departments"] = departments

    return ResolutionReport(resolved, unresolved, warnings)
