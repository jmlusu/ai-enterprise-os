from pathlib import Path

from ai_company.models.company import CompanyManifest
from ai_company.validator.reports import ValidationReport


def validate_manifest_file(manifest_path: Path) -> ValidationReport:
    report = ValidationReport(target="manifest", passed=True)

    if not manifest_path.exists():
        report.add_error(
            f"Manifest file not found: {manifest_path}", path=str(manifest_path)
        )
        return report

    if manifest_path.stat().st_size == 0:
        report.add_error(
            f"Manifest file is empty: {manifest_path}", path=str(manifest_path)
        )
        return report

    try:
        manifest = CompanyManifest.load(manifest_path)
    except (FileNotFoundError, ValueError) as e:
        report.add_error(str(e), path=str(manifest_path))
        return report

    manifest_errors = manifest.validate_manifest()
    if manifest_errors:
        for err in manifest_errors:
            report.add_error(err, path=str(manifest_path))
    else:
        report.add_info("Manifest business rules passed", path=str(manifest_path))

    if not manifest.name:
        report.add_error(
            "Manifest name is required", field="name", path=str(manifest_path)
        )
    if manifest.version:
        parts = manifest.version.split(".")
        if len(parts) not in (2, 3):
            report.add_warning(
                f"Version '{manifest.version}' does not follow semver (e.g. 1.0.0)",
                field="version",
                path=str(manifest_path),
            )
    else:
        report.add_warning(
            "No version specified in manifest", field="version", path=str(manifest_path)
        )

    if not manifest.description:
        report.add_warning(
            "No description in manifest", field="description", path=str(manifest_path)
        )

    if not manifest.company_name:
        report.add_warning(
            "No company_name in manifest", field="company_name", path=str(manifest_path)
        )

    if len(manifest.departments) > 0:
        names = [d.name for d in manifest.departments]
        if len(names) != len(set(names)):
            dupes = [n for n in names if names.count(n) > 1]
            for d in set(dupes):
                report.add_error(
                    f"Duplicate department name: {d}",
                    field="departments",
                    path=str(manifest_path),
                )
        for dept in manifest.departments:
            if not dept.name:
                report.add_error(
                    "Department with empty name",
                    field="departments",
                    path=str(manifest_path),
                )
            if dept.description and len(dept.description) < 3:
                report.add_warning(
                    f"Department '{dept.name}' has a very short description",
                    field=f"departments.{dept.name}.description",
                    path=str(manifest_path),
                )

    return report
