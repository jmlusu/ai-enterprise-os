import re
from pathlib import Path

from ai_company.validator.reports import ValidationReport

UNRESOLVED_JINJA = re.compile(r"\{\{.*?\}\}")
UNRESOLVED_KEY = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_\.]*\}")


def validate_generated_file(
    filepath: Path, context_keys: set[str] | None = None
) -> ValidationReport:
    report = ValidationReport(target=f"output:{filepath.name}", passed=True)

    if not filepath.exists():
        report.add_error(
            f"Generated file not found: {filepath.name}", path=str(filepath)
        )
        return report

    if filepath.stat().st_size == 0:
        report.add_error(
            f"Generated file is empty: {filepath.name}", path=str(filepath)
        )
        return report

    try:
        content = filepath.read_text(encoding="utf-8")
    except OSError as e:
        report.add_error(f"Cannot read generated file: {e}", path=str(filepath))
        return report

    content_length = len(content)
    if content_length < 10:
        report.add_warning(
            f"Generated file is very short ({content_length} chars)", path=str(filepath)
        )

    unresolved_jinja = UNRESOLVED_JINJA.findall(content)
    if unresolved_jinja:
        for match in unresolved_jinja[:5]:
            report.add_error(
                f"Unresolved Jinja2 placeholder in generated output: {match.strip()}",
                path=str(filepath),
            )

    unresolved_keys = UNRESOLVED_KEY.findall(content)
    if unresolved_keys:
        for match in unresolved_keys[:5]:
            report.add_warning(
                f"Possible unresolved {match} substitution key in generated output",
                path=str(filepath),
            )

    if content_length > 0 and not content.strip():
        report.add_warning(
            f"File contains only whitespace: {filepath.name}", path=str(filepath)
        )

    return report


def validate_generated_directory(output_dir: Path) -> ValidationReport:
    report = ValidationReport(target="generated_output", passed=True)

    if not output_dir.is_dir():
        report.add_error(
            f"Generated output directory not found: {output_dir}", path=str(output_dir)
        )
        return report

    expected_files = ["README.md", "README", "docs", "prompts"]
    for name in expected_files:
        path = output_dir / name
        if not path.exists():
            report.add_warning(
                f"Expected output path not found: {name}", path=str(path)
            )

    md_files = list(output_dir.rglob("*.md"))
    if not md_files:
        report.add_error(
            f"No markdown files found in {output_dir}", path=str(output_dir)
        )
    else:
        report.add_info(f"Found {len(md_files)} generated markdown file(s)")

    py_files = list(output_dir.rglob("*.py"))
    if py_files:
        report.add_info(f"Found {len(py_files)} generated Python file(s)")

    for f in md_files:
        if f.stat().st_size == 0:
            report.add_warning(
                f"Empty generated file: {f.relative_to(output_dir)}", path=str(f)
            )

    readme_dir = output_dir / "README"
    if readme_dir.is_dir():
        dept_readmes = list(readme_dir.rglob("README.md"))
        if dept_readmes:
            report.add_info(f"Found {len(dept_readmes)} department README(s)")

    return report
