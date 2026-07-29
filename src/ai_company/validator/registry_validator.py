from pathlib import Path

from ai_company.registry.loader import load_registry_files
from ai_company.registry.parser import parse_registry
from ai_company.registry.resolver import resolve
from ai_company.registry.validator import validate_parsed_data
from ai_company.validator.reports import ValidationReport


DEPARTMENT_NAMES = [
    "executive", "strategic", "technical", "marketing",
    "sales", "research", "product",
]


def validate_registry_integrity(company_dir: Path) -> ValidationReport:
    report = ValidationReport(target="registry", passed=True)

    if not company_dir.is_dir():
        report.add_error(f"Company directory not found: {company_dir}", path=str(company_dir))
        return report

    load_result = load_registry_files(company_dir)
    for err in load_result.errors:
        report.add_error(err, path=str(company_dir / "*.yaml"))
    if not load_result.success:
        return report

    parsed = parse_registry(load_result.data)

    validation = validate_parsed_data(parsed)
    for err in validation.errors:
        report.add_error(err)
    for w in validation.warnings:
        report.add_warning(w)
    if not validation.valid:
        report.passed = False

    resolution = resolve(parsed)
    if not resolution.success:
        for ref in resolution.unresolved_refs:
            report.add_warning(
                f"Department '{ref}' not defined in departments.yaml (will use stub)",
                field="department_names",
            )
    for w in resolution.warnings:
        report.add_warning(w)

    vision = parsed.get("vision", {})
    if not vision.get("name"):
        report.add_error("Vision name is required", field="vision.name")

    company_yaml = load_result.data.get("company", {})
    dept_list = company_yaml.get("departments", [])
    if not isinstance(dept_list, list):
        report.add_error("company.yaml 'departments' must be a list", field="company.departments")
    elif len(dept_list) < 1:
        report.add_warning("No departments defined in company.yaml", field="company.departments")

    depts_from_yaml = load_result.data.get("departments", {})
    if isinstance(dept_list, list):
        for dept_name in dept_list:
            name_lower = dept_name.lower() if isinstance(dept_name, str) else str(dept_name)
            if name_lower not in depts_from_yaml:
                report.add_warning(
                    f"Department '{dept_name}' has no roles defined in departments.yaml",
                    field=f"departments.{dept_name}",
                )

    board = load_result.data.get("board", {})
    if board and isinstance(board, dict) and board.get("members"):
        members = board["members"]
        if isinstance(members, list) and len(members) > 0:
            report.add_info(f"Board has {len(members)} member(s)")

    return report
