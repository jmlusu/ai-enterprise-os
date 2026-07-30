"""Tests for the Department Generator (Phase 4, Sprint 3)."""

from pathlib import Path

import pytest
import yaml

from ai_company.company.department_generator import DepartmentGenerator
from ai_company.models.company import (
    CompanyManifest,
    CompanyRegistry,
    Culture,
    DepartmentData,
    ManifestDepartment,
    Role,
    Strategy,
    VisionData,
)


@pytest.fixture
def manifest() -> CompanyManifest:
    return CompanyManifest(
        name="TestCo Inc",
        company_name="TestCo Inc",
        description="A test company",
        departments=[
            ManifestDepartment(
                name="engineering",
                display_name="Engineering",
                description="Build stuff",
            ),
            ManifestDepartment(
                name="marketing", display_name="Marketing", description="Sell stuff"
            ),
        ],
    )


@pytest.fixture
def registry(manifest: CompanyManifest) -> CompanyRegistry:
    return CompanyRegistry(
        vision=VisionData(name="TestCo", company_name="TestCo Inc"),
        departments={
            "engineering": DepartmentData(
                name="engineering",
                roles=[
                    Role(title="Software Engineer", description="Builds features"),
                    Role(title="Senior Engineer", description="Leads projects"),
                ],
            ),
        },
        strategy=Strategy(
            name="Growth",
            description="Expand market presence.",
            objectives=["Launch v2", "Hire more engineers"],
        ),
        culture=Culture(values=["Innovation"]),
    )


@pytest.fixture
def empty_manifest() -> CompanyManifest:
    return CompanyManifest(
        name="EmptyCo",
        company_name="EmptyCo",
        description="",
    )


@pytest.fixture
def empty_registry(empty_manifest: CompanyManifest) -> CompanyRegistry:
    return CompanyRegistry(
        vision=VisionData(name="EmptyCo"),
    )


class TestDepartmentGenerator:
    def test_generate_with_departments(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = DepartmentGenerator(registry, manifest)
        result = gen.generate()
        assert len(result.departments) == 2
        assert result.summary()["departments"] == 2

    def test_generate_with_empty_manifest(
        self, empty_registry: CompanyRegistry, empty_manifest: CompanyManifest
    ) -> None:
        gen = DepartmentGenerator(empty_registry, empty_manifest)
        result = gen.generate()
        assert len(result.departments) == 0

    def test_each_package_has_all_artifacts(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = DepartmentGenerator(registry, manifest)
        result = gen.generate()
        for pkg in result.departments:
            assert "slug" in pkg
            assert "yaml" in pkg
            assert "readme_md" in pkg
            assert "prompt_md" in pkg
            assert "agents_md" in pkg

    def test_yaml_contains_name_and_display_name(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = DepartmentGenerator(registry, manifest)
        result = gen.generate()
        eng = next(p for p in result.departments if p["name"] == "engineering")
        assert eng["yaml"]["name"] == "engineering"
        assert eng["yaml"]["display_name"] == "Engineering"

    def test_readme_contains_display_name(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = DepartmentGenerator(registry, manifest)
        result = gen.generate()
        eng = next(p for p in result.departments if p["name"] == "engineering")
        assert "Engineering" in eng["readme_md"]

    def test_readme_contains_description(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = DepartmentGenerator(registry, manifest)
        result = gen.generate()
        eng = next(p for p in result.departments if p["name"] == "engineering")
        assert "Build stuff" in eng["readme_md"]

    def test_prompt_contains_company_name(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = DepartmentGenerator(registry, manifest)
        result = gen.generate()
        eng = next(p for p in result.departments if p["name"] == "engineering")
        assert "TestCo Inc" in eng["prompt_md"]

    def test_prompt_contains_roles(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = DepartmentGenerator(registry, manifest)
        result = gen.generate()
        eng = next(p for p in result.departments if p["name"] == "engineering")
        assert "Software Engineer" in eng["prompt_md"]

    def test_agents_md_contains_roles(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = DepartmentGenerator(registry, manifest)
        result = gen.generate()
        eng = next(p for p in result.departments if p["name"] == "engineering")
        assert "Software Engineer" in eng["agents_md"]

    def test_validate_valid(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = DepartmentGenerator(registry, manifest)
        errors = gen.validate()
        assert errors == []

    def test_validate_empty(
        self, empty_registry: CompanyRegistry, empty_manifest: CompanyManifest
    ) -> None:
        gen = DepartmentGenerator(empty_registry, empty_manifest)
        errors = gen.validate()
        assert len(errors) > 0

    def test_write_artifacts(
        self, registry: CompanyRegistry, manifest: CompanyManifest, tmp_path: Path
    ) -> None:
        gen = DepartmentGenerator(registry, manifest)
        result = gen.generate()
        created = gen.write_artifacts(result, tmp_path)
        assert len(created) == 8  # 2 departments * 4 files each
        assert all(p.exists() for p in created)

    def test_written_yaml_is_valid(
        self, registry: CompanyRegistry, manifest: CompanyManifest, tmp_path: Path
    ) -> None:
        gen = DepartmentGenerator(registry, manifest)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        yaml_path = tmp_path / "departments" / "engineering" / "department.yaml"
        assert yaml_path.exists()
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert data["name"] == "engineering"
        assert data["display_name"] == "Engineering"

    def test_written_readme_exists(
        self, registry: CompanyRegistry, manifest: CompanyManifest, tmp_path: Path
    ) -> None:
        gen = DepartmentGenerator(registry, manifest)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        readme_path = tmp_path / "departments" / "engineering" / "README.md"
        assert readme_path.exists()
        assert "Engineering" in readme_path.read_text(encoding="utf-8")

    def test_written_prompt_exists(
        self, registry: CompanyRegistry, manifest: CompanyManifest, tmp_path: Path
    ) -> None:
        gen = DepartmentGenerator(registry, manifest)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        prompt_path = tmp_path / "departments" / "engineering" / "prompt.md"
        assert prompt_path.exists()

    def test_written_agents_exists(
        self, registry: CompanyRegistry, manifest: CompanyManifest, tmp_path: Path
    ) -> None:
        gen = DepartmentGenerator(registry, manifest)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        agents_path = tmp_path / "departments" / "engineering" / "agents.md"
        assert agents_path.exists()
        assert "Software Engineer" in agents_path.read_text(encoding="utf-8")

    def test_marketing_department_in_readme(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = DepartmentGenerator(registry, manifest)
        result = gen.generate()
        mktg = next(p for p in result.departments if p["name"] == "marketing")
        assert "Marketing" in mktg["readme_md"]
        assert "Sell stuff" in mktg["readme_md"]
