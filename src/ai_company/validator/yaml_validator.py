from pathlib import Path

from ai_company.registry.loader import REGISTRY_FILES, load_yaml
from ai_company.validator.reports import ValidationReport


def validate_yaml_file(filepath: Path) -> ValidationReport:
    report = ValidationReport(target=f"yaml:{filepath.name}", passed=True)

    if not filepath.exists():
        report.add_error(f"File not found: {filepath}", path=str(filepath))
        return report

    if filepath.stat().st_size == 0:
        report.add_warning(f"Empty YAML file: {filepath.name}", path=str(filepath))
        return report

    try:
        data = load_yaml(filepath)
        if data is None:
            report.add_warning(f"File returned no data: {filepath.name}", path=str(filepath))
            return report
        report.add_info(f"Parsed {len(data)} top-level key(s)", path=str(filepath))
    except ValueError as e:
        report.add_error(str(e), path=str(filepath))
        return report
    except OSError as e:
        report.add_error(f"Unexpected error parsing {filepath.name}: {e}", path=str(filepath))
        return report

    return report


def validate_yaml_directory(registry_dir: Path) -> ValidationReport:
    report = ValidationReport(target="yaml:registry", passed=True)

    if not registry_dir.is_dir():
        report.add_error(f"Registry directory not found: {registry_dir}", path=str(registry_dir))
        return report

    for filename in REGISTRY_FILES:
        filepath = registry_dir / filename
        if not filepath.exists():
            report.add_warning(f"Optional registry file not found: {filename}", path=str(filepath))
            continue
        file_report = validate_yaml_file(filepath)
        report.errors.extend(file_report.errors)
        report.warnings.extend(file_report.warnings)
        report.infos.extend(file_report.infos)
        report.total_checks += file_report.total_checks
        if not file_report.passed:
            report.passed = False

    return report
