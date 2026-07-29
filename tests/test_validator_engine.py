import shutil
import tempfile
from pathlib import Path
from typing import Iterator

import pytest
import yaml

from ai_company.validator.engine import ValidatorEngine
from ai_company.validator.manifest_validator import validate_manifest_file
from ai_company.validator.output_validator import (
    validate_generated_directory,
    validate_generated_file,
)
from ai_company.validator.registry_validator import validate_registry_integrity
from ai_company.validator.reports import ValidationIssue, ValidationReport, ValidatorResult
from ai_company.validator.template_validator import (
    validate_jinja_template,
    validate_templates_directory,
)
from ai_company.validator.yaml_validator import validate_yaml_directory, validate_yaml_file


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_dir() -> Iterator[Path]:
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def temp_yaml_file(temp_dir: Path) -> Path:
    f = temp_dir / "test.yaml"
    f.write_text("name: test\nvalue: 42\n", encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# Pydantic report model tests
# ---------------------------------------------------------------------------


class TestValidationIssue:
    def test_minimal(self) -> None:
        issue = ValidationIssue(message="something broke")
        assert issue.message == "something broke"
        assert issue.severity == "error"
        assert issue.field == ""
        assert issue.path is None

    def test_full(self) -> None:
        issue = ValidationIssue(
            message="bad field", severity="warning", field="name", path="file.yaml"
        )
        assert issue.severity == "warning"
        assert issue.field == "name"
        assert issue.path == "file.yaml"


class TestValidationReport:
    def test_defaults(self) -> None:
        r = ValidationReport(target="test", passed=True)
        assert r.target == "test"
        assert r.passed
        assert r.errors == []
        assert r.total_checks == 0

    def test_add_error(self) -> None:
        r = ValidationReport(target="t", passed=True)
        r.add_error("bad", field="x", path="f.yaml")
        assert not r.passed
        assert len(r.errors) == 1
        assert r.errors[0].message == "bad"
        assert r.errors[0].field == "x"
        assert r.total_checks == 1

    def test_add_warning(self) -> None:
        r = ValidationReport(target="t", passed=True)
        r.add_warning("warning")
        assert r.passed
        assert len(r.warnings) == 1
        assert r.total_checks == 1

    def test_add_info(self) -> None:
        r = ValidationReport(target="t", passed=True)
        r.add_info("info")
        assert r.passed
        assert len(r.infos) == 1
        assert r.total_checks == 1


class TestValidatorResult:
    def test_all_passed(self) -> None:
        r = ValidatorResult(reports=[
            ValidationReport(target="a", passed=True),
            ValidationReport(target="b", passed=True),
        ])
        assert r.passed
        assert r.total_errors == 0
        assert r.summary().startswith("Validator Engine [PASSED]")

    def test_any_failed(self) -> None:
        r = ValidatorResult(reports=[
            ValidationReport(target="a", passed=True),
            ValidationReport(target="b", passed=False),
        ])
        assert not r.passed

    def test_totals(self) -> None:
        a = ValidationReport(target="a", passed=False)
        a.add_error("e1")
        a.add_warning("w1")
        b = ValidationReport(target="b", passed=True)
        b.add_info("i1")
        r = ValidatorResult(reports=[a, b])
        assert r.total_errors == 1
        assert r.total_warnings == 1
        assert r.total_checks == 3

    def test_timestamp(self) -> None:
        r = ValidatorResult()
        assert r.timestamp is not None

    def test_engine_version(self) -> None:
        r = ValidatorResult()
        assert r.engine_version == "1.0.0"


# ---------------------------------------------------------------------------
# YAML Validator tests
# ---------------------------------------------------------------------------


class TestYamlValidator:
    def test_valid_yaml_file(self, temp_yaml_file: Path) -> None:
        report = validate_yaml_file(temp_yaml_file)
        assert report.passed
        assert report.target == f"yaml:{temp_yaml_file.name}"

    def test_missing_yaml_file(self, temp_dir: Path) -> None:
        missing = temp_dir / "nonexistent.yaml"
        report = validate_yaml_file(missing)
        assert not report.passed
        assert any("not found" in e.message for e in report.errors)

    def test_empty_yaml_file(self, temp_dir: Path) -> None:
        f = temp_dir / "empty.yaml"
        f.write_text("")
        report = validate_yaml_file(f)
        assert report.passed
        assert any("Empty" in w.message for w in report.warnings)

    def test_invalid_yaml_syntax(self, temp_dir: Path) -> None:
        f = temp_dir / "bad.yaml"
        f.write_text(": broken yaml :\n  indentation:", encoding="utf-8")
        report = validate_yaml_file(f)
        assert not report.passed
        assert any("YAML syntax error" in e.message for e in report.errors)

    def test_validate_yaml_directory(self) -> None:
        report = validate_yaml_directory(Path("company"))
        assert report.passed
        assert report.target == "yaml:registry"

    def test_validate_nonexistent_directory(self, temp_dir: Path) -> None:
        report = validate_yaml_directory(temp_dir / "nope")
        assert not report.passed
        assert any("not found" in e.message for e in report.errors)

    def test_validate_mixed_directory(self, temp_dir: Path) -> None:
        (temp_dir / "company.yaml").write_text("name: test\n", encoding="utf-8")
        report = validate_yaml_directory(temp_dir)
        assert report.passed


# ---------------------------------------------------------------------------
# Registry Validator tests
# ---------------------------------------------------------------------------


class TestRegistryValidator:
    def test_valid_registry(self) -> None:
        report = validate_registry_integrity(Path("company"))
        assert report.passed
        assert report.target == "registry"

    def test_nonexistent_directory(self, temp_dir: Path) -> None:
        report = validate_registry_integrity(temp_dir / "nope")
        assert not report.passed
        assert any("not found" in e.message for e in report.errors)

    def test_empty_directory(self, temp_dir: Path) -> None:
        report = validate_registry_integrity(temp_dir)
        assert not report.passed

    def test_partial_registry(self, temp_dir: Path) -> None:
        (temp_dir / "company.yaml").write_text(
            "name: Test\ncompany_name: TC\ndepartments:\n  - eng\n", encoding="utf-8"
        )
        (temp_dir / "departments.yaml").write_text(
            "eng:\n  - Dev: Developer\n", encoding="utf-8"
        )
        report = validate_registry_integrity(temp_dir)
        assert report.passed

    def test_registry_missing_department_roles(self, temp_dir: Path) -> None:
        (temp_dir / "company.yaml").write_text(
            "name: Test\ncompany_name: TC\ndepartments:\n  - eng\n  - sales\n",
            encoding="utf-8",
        )
        (temp_dir / "departments.yaml").write_text(
            "eng:\n  - Dev: Developer\n", encoding="utf-8"
        )
        report = validate_registry_integrity(temp_dir)
        assert report.passed
        assert any("sales" in w.message for w in report.warnings)


# ---------------------------------------------------------------------------
# Template Validator tests
# ---------------------------------------------------------------------------


class TestTemplateValidator:
    def test_valid_jinja_template(self, temp_dir: Path) -> None:
        f = temp_dir / "test.j2"
        f.write_text("Hello {{ name }}!", encoding="utf-8")
        report = validate_jinja_template(f)
        assert report.passed

    def test_invalid_jinja_syntax(self, temp_dir: Path) -> None:
        f = temp_dir / "bad.j2"
        f.write_text("{% bad syntax %}", encoding="utf-8")
        report = validate_jinja_template(f)
        assert not report.passed
        assert any("Jinja2 syntax error" in e.message for e in report.errors)

    def test_missing_template(self, temp_dir: Path) -> None:
        missing = temp_dir / "missing.j2"
        report = validate_jinja_template(missing)
        assert not report.passed
        assert any("not found" in e.message for e in report.errors)

    def test_empty_template(self, temp_dir: Path) -> None:
        f = temp_dir / "empty.j2"
        f.write_text("")
        report = validate_jinja_template(f)
        assert report.passed
        assert any("Empty" in w.message for w in report.warnings)

    def test_template_with_for_loop(self, temp_dir: Path) -> None:
        f = temp_dir / "loop.j2"
        f.write_text(
            "{% for item in items %}{{ item }}{% endfor %}",
            encoding="utf-8",
        )
        report = validate_jinja_template(f)
        assert report.passed

    def test_real_templates_directory(self) -> None:
        report = validate_templates_directory(Path("templates"))
        assert report.passed
        assert report.target == "templates"

    def test_nonexistent_templates_directory(self, temp_dir: Path) -> None:
        report = validate_templates_directory(temp_dir / "nope")
        assert not report.passed
        assert any("not found" in e.message for e in report.errors)

    def test_template_with_if_block(self, temp_dir: Path) -> None:
        f = temp_dir / "cond.j2"
        f.write_text("{% if show %}{{ value }}{% endif %}", encoding="utf-8")
        report = validate_jinja_template(f)
        assert report.passed


# ---------------------------------------------------------------------------
# Manifest Validator tests
# ---------------------------------------------------------------------------


class TestManifestValidator:
    def test_valid_manifest(self) -> None:
        report = validate_manifest_file(Path("config/company/company.yaml"))
        assert report.passed
        assert report.target == "manifest"

    def test_missing_manifest(self, temp_dir: Path) -> None:
        report = validate_manifest_file(temp_dir / "nonexistent.yaml")
        assert not report.passed
        assert any("not found" in e.message for e in report.errors)

    def test_empty_manifest(self, temp_dir: Path) -> None:
        f = temp_dir / "manifest.yaml"
        f.write_text("")
        report = validate_manifest_file(f)
        assert not report.passed
        assert any("empty" in e.message for e in report.errors)

    def test_invalid_yaml_in_manifest(self, temp_dir: Path) -> None:
        f = temp_dir / "manifest.yaml"
        f.write_text(": broken :\n  indentation:")
        report = validate_manifest_file(f)
        assert not report.passed
        assert any("YAML syntax error" in e.message for e in report.errors)

    def test_manifest_missing_name(self, temp_dir: Path) -> None:
        f = temp_dir / "manifest.yaml"
        f.write_text("version: 1.0\ndepartments: []\n", encoding="utf-8")
        report = validate_manifest_file(f)
        assert not report.passed

    def test_manifest_with_duplicate_departments(self, temp_dir: Path) -> None:
        f = temp_dir / "manifest.yaml"
        f.write_text(
            "name: Test\n"
            "version: 1.0.0\n"
            "departments:\n"
            "  - name: eng\n"
            "  - name: eng\n",
            encoding="utf-8",
        )
        report = validate_manifest_file(f)
        assert not report.passed
        assert any("Duplicate" in e.message for e in report.errors)

    def test_manifest_no_departments(self, temp_dir: Path) -> None:
        f = temp_dir / "manifest.yaml"
        f.write_text("name: Test\nversion: 1.0.0\n", encoding="utf-8")
        report = validate_manifest_file(f)
        assert not report.passed

    def test_manifest_non_semver_version(self, temp_dir: Path) -> None:
        f = temp_dir / "manifest.yaml"
        f.write_text(
            "name: Test\n"
            "version: abc\n"
            "departments:\n"
            "  - name: eng\n",
            encoding="utf-8",
        )
        report = validate_manifest_file(f)
        assert report.passed
        assert any("does not follow semver" in w.message for w in report.warnings)


# ---------------------------------------------------------------------------
# Output Validator tests
# ---------------------------------------------------------------------------


class TestOutputValidator:
    def test_generated_file_exists(self, temp_dir: Path) -> None:
        f = temp_dir / "output.md"
        f.write_text("# Hello World\n", encoding="utf-8")
        report = validate_generated_file(f)
        assert report.passed

    def test_generated_file_missing(self, temp_dir: Path) -> None:
        report = validate_generated_file(temp_dir / "missing.md")
        assert not report.passed
        assert any("not found" in e.message for e in report.errors)

    def test_generated_file_empty(self, temp_dir: Path) -> None:
        f = temp_dir / "empty.md"
        f.write_text("")
        report = validate_generated_file(f)
        assert not report.passed
        assert any("empty" in e.message for e in report.errors)

    def test_generated_file_with_unresolved_jinja(self, temp_dir: Path) -> None:
        f = temp_dir / "bad.md"
        f.write_text("# {{ title }}\n\n{{ body }}\n", encoding="utf-8")
        report = validate_generated_file(f)
        assert not report.passed
        assert any("Unresolved Jinja" in e.message for e in report.errors)

    def test_generated_file_with_unresolved_key(self, temp_dir: Path) -> None:
        f = temp_dir / "key.md"
        f.write_text("# {title}\n{body}\n", encoding="utf-8")
        report = validate_generated_file(f)
        assert report.passed
        assert any("unresolved" in w.message for w in report.warnings)

    def test_generated_file_very_short(self, temp_dir: Path) -> None:
        f = temp_dir / "short.md"
        f.write_text("a", encoding="utf-8")
        report = validate_generated_file(f)
        assert report.passed
        assert any("very short" in w.message for w in report.warnings)

    def test_generated_directory_real(self) -> None:
        report = validate_generated_directory(Path("generated"))
        if report.passed:
            assert report.target == "generated_output"
        else:
            assert any("not found" in e.message for e in report.errors
                       or "No markdown" in e.message for e in report.errors)

    def test_generated_directory_nonexistent(self, temp_dir: Path) -> None:
        report = validate_generated_directory(temp_dir / "nope")
        assert not report.passed
        assert any("not found" in e.message for e in report.errors)


# ---------------------------------------------------------------------------
# ValidatorEngine integration tests
# ---------------------------------------------------------------------------


class TestValidatorEngine:
    def test_validate_all(self) -> None:
        engine = ValidatorEngine()
        result = engine.validate_all()
        assert isinstance(result, ValidatorResult)
        assert len(result.reports) == 5
        assert all(r.target in ["yaml:registry", "registry", "templates", "manifest", "generated_output"]
                   for r in result.reports)

    def test_validate_all_passed(self) -> None:
        engine = ValidatorEngine()
        result = engine.validate_all()
        assert result.summary() is not None

    def test_validate_yaml(self) -> None:
        engine = ValidatorEngine()
        report = engine.validate_yaml()
        assert report.target == "yaml:registry"

    def test_validate_registry(self) -> None:
        engine = ValidatorEngine()
        report = engine.validate_registry()
        assert report.target == "registry"

    def test_validate_templates(self) -> None:
        engine = ValidatorEngine()
        report = engine.validate_templates()
        assert report.target == "templates"

    def test_validate_manifest(self) -> None:
        engine = ValidatorEngine()
        report = engine.validate_manifest()
        assert report.target == "manifest"

    def test_validate_output(self) -> None:
        engine = ValidatorEngine()
        report = engine.validate_output()
        assert report.target == "generated_output"

    def test_custom_paths(self, temp_dir: Path) -> None:
        (temp_dir / "company.yaml").write_text("name: Custom\n", encoding="utf-8")
        engine = ValidatorEngine(
            company_dir=temp_dir,
            manifest_path=temp_dir / "company.yaml",
            templates_dir=temp_dir,
            output_dir=temp_dir,
        )
        result = engine.validate_all()
        assert len(result.reports) == 5
        assert isinstance(result, ValidatorResult)


# ---------------------------------------------------------------------------
# Real-world data integration tests
# ---------------------------------------------------------------------------


class TestRealDataIntegration:
    def test_real_yaml_validates(self) -> None:
        report = validate_yaml_file(Path("company/company.yaml"))
        assert report.passed

    def test_real_departments_yaml_validates(self) -> None:
        report = validate_yaml_file(Path("company/departments.yaml"))
        assert report.passed

    def test_all_templates_valid(self) -> None:
        for t in ["README.md.j2", "department_README.md.j2",
                   "doc_placeholder.md.j2", "prompt_placeholder.md.j2",
                   "test_placeholder.py.j2"]:
            report = validate_jinja_template(Path("templates") / t)
            assert report.passed, f"Template {t} failed: {report.errors}"

    def test_full_validation_pipeline(self) -> None:
        engine = ValidatorEngine()
        result = engine.validate_all()
        assert isinstance(result, ValidatorResult)
        yaml_report = result.reports[0]
        reg_report = result.reports[1]
        tmpl_report = result.reports[2]
        man_report = result.reports[3]
        out_report = result.reports[4]
        assert yaml_report.target == "yaml:registry"
        assert reg_report.target == "registry"
        assert tmpl_report.target == "templates"
        assert man_report.target == "manifest"
        assert out_report.target == "generated_output"
