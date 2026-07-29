import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from ai_company.bootstrap.bootstrap import BootstrapGenerator, BootstrapResult
from ai_company.models.company import CompanyManifest
from ai_company.registry.registry import RegistryEngine


@pytest.fixture(autouse=True)
def reload_registry() -> None:
    RegistryEngine().reload()


@pytest.fixture
def temp_dir() -> Iterator[Path]:
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def isolated_project(temp_dir: Path) -> Iterator[Path]:
    src_company = Path("company")
    dst_company = temp_dir / "company"
    shutil.copytree(str(src_company), str(dst_company))

    src_config = Path("config")
    dst_config = temp_dir / "config"
    shutil.copytree(str(src_config), str(dst_config))

    src_templates = Path("templates")
    dst_templates = temp_dir / "templates"
    shutil.copytree(str(src_templates), str(dst_templates))

    src_tests = Path("tests")
    dst_tests = temp_dir / "tests"
    shutil.copytree(str(src_tests), str(dst_tests))

    yield temp_dir


class TestBootstrapGenerator:
    def test_success(self) -> None:
        generator = BootstrapGenerator()
        result = generator.run()
        assert result.success
        assert len(result.errors) == 0

    def test_creates_main_readme(self) -> None:
        generator = BootstrapGenerator()
        result = generator.run()
        assert result.success
        readme_path = Path("generated/README.md")
        assert any(readme_path.name in f for f in result.created_files) or readme_path.exists()

    def test_creates_department_readmes(self) -> None:
        generator = BootstrapGenerator()
        result = generator.run()
        assert result.success
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        for dept in manifest.departments:
            expected = Path("generated") / "README" / dept.name / "README.md"
            assert expected.exists(), f"Missing department README: {expected}"

    def test_creates_documentation_placeholders(self) -> None:
        generator = BootstrapGenerator()
        result = generator.run()
        assert result.success
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        for dept in manifest.departments:
            expected = Path("generated") / "docs" / dept.name / "README.md"
            assert expected.exists(), f"Missing doc placeholder: {expected}"

    def test_creates_prompt_placeholders(self) -> None:
        generator = BootstrapGenerator()
        result = generator.run()
        assert result.success
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        for dept in manifest.departments:
            expected = Path("generated") / "prompts" / dept.name / "README.md"
            assert expected.exists(), f"Missing prompt placeholder: {expected}"

    def test_creates_test_placeholders(self) -> None:
        generator = BootstrapGenerator()
        result = generator.run()
        assert result.success
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        for dept in manifest.departments:
            expected = Path("tests") / f"test_{dept.name}.py"
            assert expected.exists(), f"Missing test placeholder: {expected}"

    def test_rendered_content_contains_department_name(self) -> None:
        generator = BootstrapGenerator()
        result = generator.run()
        assert result.success
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        for dept in manifest.departments:
            readme = Path("generated") / "README" / dept.name / "README.md"
            content = readme.read_text(encoding="utf-8")
            display = dept.display_name or dept.name.title()
            assert display in content

    def test_is_idempotent(self) -> None:
        generator = BootstrapGenerator()
        result1 = generator.run()
        assert result1.success
        files_after_first = set()
        for f in result1.created_files:
            p = Path(f)
            files_after_first.add((str(p), p.read_text(encoding="utf-8") if p.exists() else ""))

        RegistryEngine().reload()
        result2 = generator.run()
        assert result2.success
        files_after_second = set()
        for f in result2.created_files:
            p = Path(f)
            files_after_second.add((str(p), p.read_text(encoding="utf-8") if p.exists() else ""))

        assert files_after_first == files_after_second

    def test_fails_when_manifest_missing(self, temp_dir: Path) -> None:
        generator = BootstrapGenerator(
            company_dir=temp_dir,
            manifest_path=temp_dir / "nonexistent.yaml",
            templates_dir=temp_dir,
            output_dir=temp_dir / "out",
            tests_dir=temp_dir / "tests",
        )
        result = generator.run()
        assert not result.success
        assert len(result.errors) > 0

    def test_isolated_project_success(self, isolated_project: Path) -> None:
        company_dir = isolated_project / "company"
        manifest_path = isolated_project / "config" / "company" / "company.yaml"
        templates_dir = isolated_project / "templates"
        output_dir = isolated_project / "generated"
        tests_dir = isolated_project / "tests"

        generator = BootstrapGenerator(
            company_dir=company_dir,
            manifest_path=manifest_path,
            templates_dir=templates_dir,
            output_dir=output_dir,
            tests_dir=tests_dir,
        )
        result = generator.run()
        assert result.success
        assert len(result.created_files) > 0


class TestBootstrapResult:
    def test_defaults(self) -> None:
        result = BootstrapResult(success=True, created_files=[], errors=[], warnings=[])
        assert result.success
        assert result.created_files == []
        assert result.errors == []
        assert result.warnings == []
        assert result.registry_result is None

    def test_failure_has_no_created_files(self) -> None:
        result = BootstrapResult(success=False, created_files=[], errors=["oops"], warnings=[])
        assert not result.success
        assert result.errors == ["oops"]
