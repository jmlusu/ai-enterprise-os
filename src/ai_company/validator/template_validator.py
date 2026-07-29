from pathlib import Path

from jinja2 import Environment, TemplateError
from jinja2.exceptions import TemplateSyntaxError
from jinja2.meta import find_undeclared_variables

from ai_company.validator.reports import ValidationReport

REQUIRED_TEMPLATES = [
    "README.md.j2",
    "department_README.md.j2",
    "doc_placeholder.md.j2",
    "prompt_placeholder.md.j2",
    "test_placeholder.py.j2",
]


def validate_jinja_template(filepath: Path) -> ValidationReport:
    report = ValidationReport(target=f"template:{filepath.name}", passed=True)

    if not filepath.exists():
        report.add_error(f"Template file not found: {filepath.name}", path=str(filepath))
        return report

    if filepath.stat().st_size == 0:
        report.add_warning(f"Empty template file: {filepath.name}", path=str(filepath))
        return report

    try:
        source = filepath.read_text(encoding="utf-8")
    except Exception as e:
        report.add_error(f"Cannot read template file: {e}", path=str(filepath))
        return report

    try:
        env = Environment()
        ast = env.parse(source)
    except TemplateSyntaxError as e:
        report.add_error(
            f"Jinja2 syntax error at line {e.lineno}: {e.message}",
            path=str(filepath),
            field=f"line:{e.lineno}",
        )
        return report
    except TemplateError as e:
        report.add_error(f"Jinja2 error: {e}", path=str(filepath))
        return report

    if report.passed:
        report.add_info(f"Template parses successfully", path=str(filepath))

    return report


def validate_template_variables(filepath: Path, known_context_keys: set[str]) -> ValidationReport:
    report = ValidationReport(target=f"template_vars:{filepath.name}", passed=True)

    if not filepath.exists():
        report.add_error(f"Template file not found: {filepath.name}", path=str(filepath))
        return report

    try:
        source = filepath.read_text(encoding="utf-8")
    except Exception:
        return report

    try:
        env = Environment()
        ast = env.parse(source)
        undeclared = find_undeclared_variables(ast)
    except TemplateError:
        return report

    if undeclared:
        unknown = undeclared - known_context_keys
        if unknown:
            for var in sorted(unknown):
                report.add_warning(
                    f"Template uses undeclared variable: {var}",
                    field=f"variable:{var}",
                    path=str(filepath),
                )

    return report


def validate_templates_directory(templates_dir: Path) -> ValidationReport:
    report = ValidationReport(target="templates", passed=True)

    if not templates_dir.is_dir():
        report.add_error(f"Templates directory not found: {templates_dir}", path=str(templates_dir))
        return report

    for template_name in REQUIRED_TEMPLATES:
        filepath = templates_dir / template_name
        if not filepath.exists():
            report.add_warning(f"Expected template not found: {template_name}", path=str(filepath))
            continue
        file_report = validate_jinja_template(filepath)
        report.errors.extend(file_report.errors)
        report.warnings.extend(file_report.warnings)
        report.infos.extend(file_report.infos)
        report.total_checks += file_report.total_checks
        if not file_report.passed:
            report.passed = False

    for filepath in sorted(templates_dir.glob("*.j2")):
        if filepath.name not in REQUIRED_TEMPLATES:
            report.add_info(f"Additional template found: {filepath.name}", path=str(filepath))

    for filepath in sorted(templates_dir.glob("*.j2")):
        if filepath.stat().st_size == 0:
            report.add_warning(f"Empty template: {filepath.name}", path=str(filepath))

    return report


def find_unresolved_placeholders(filepath: Path, context_keys: set[str]) -> ValidationReport:
    report = ValidationReport(target=f"placeholders:{filepath.name}", passed=True)

    if not filepath.exists() or filepath.stat().st_size == 0:
        return report

    try:
        source = filepath.read_text(encoding="utf-8")
    except Exception:
        return report

    env = Environment()
    try:
        ast = env.parse(source)
        undeclared = find_undeclared_variables(ast)
    except TemplateError:
        return report

    missing = undeclared - context_keys
    if missing:
        for var in sorted(missing):
            report.add_warning(
                f"Template has unresolved variable: {var}",
                field=f"variable:{var}",
                path=str(filepath),
            )

    return report
