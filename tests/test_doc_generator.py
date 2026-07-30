"""Tests for the Documentation Generator (Phase 8, Sprint 3)."""

from pathlib import Path

import pytest

from ai_company.company.doc_generator import DocGenerator
from ai_company.models.company import (
    CompanyManifest,
    CompanyRegistry,
    Culture,
    DepartmentData,
    ExecutiveEntry,
    Role,
    SpecialistEntry,
    Strategy,
    VisionData,
    WorkflowEntry,
)


@pytest.fixture
def manifest() -> CompanyManifest:
    return CompanyManifest(
        name="TestCo Inc",
        company_name="TestCo Inc",
        description="A test company",
    )


@pytest.fixture
def registry(manifest: CompanyManifest) -> CompanyRegistry:
    return CompanyRegistry(
        vision=VisionData(name="TestCo", company_name="TestCo Inc"),
        executives=[
            ExecutiveEntry(
                name="Alice CEO",
                title="CEO",
                responsibilities=["Lead"],
                kpis=["Revenue growth"],
            ),
        ],
        departments={
            "engineering": DepartmentData(
                name="engineering",
                roles=[Role(title="Engineer", description="Builds stuff")],
            ),
        },
        specialists=[
            SpecialistEntry(name="Bob", expertise="ML"),
        ],
        workflows=[
            WorkflowEntry(
                name="Onboarding",
                description="New hire process",
                steps=["Step 1", "Step 2"],
            ),
        ],
        strategy=Strategy(name="Growth", description="Grow", objectives=["Launch"]),
        culture=Culture(values=["Innovation"]),
    )


@pytest.fixture
def empty_registry() -> CompanyRegistry:
    return CompanyRegistry(vision=VisionData(name="EmptyCo"))


class TestDocGenerator:
    def test_generate_with_entities(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = DocGenerator(registry, manifest)
        result = gen.generate()
        assert result.summary()["pages"] == 4  # exec + dept + specialist + workflow

    def test_generate_with_empty_registry(
        self, empty_registry: CompanyRegistry
    ) -> None:
        gen = DocGenerator(empty_registry)
        result = gen.generate()
        assert len(result.pages) == 0

    def test_pages_have_types(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = DocGenerator(registry, manifest)
        result = gen.generate()
        types = {p["type"] for p in result.pages}
        assert types == {"executive", "department", "specialist", "workflow"}

    def test_page_markdown_contains_title(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = DocGenerator(registry, manifest)
        result = gen.generate()
        exec_page = next(p for p in result.pages if p["type"] == "executive")
        assert "# Alice CEO" in exec_page["markdown"]

    def test_validate_valid(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = DocGenerator(registry, manifest)
        errors = gen.validate()
        assert errors == []

    def test_validate_empty(self, empty_registry: CompanyRegistry) -> None:
        gen = DocGenerator(empty_registry)
        errors = gen.validate()
        assert len(errors) > 0

    def test_write_artifacts(
        self, registry: CompanyRegistry, manifest: CompanyManifest, tmp_path: Path
    ) -> None:
        gen = DocGenerator(registry, manifest)
        result = gen.generate()
        created = gen.write_artifacts(result, tmp_path)
        assert len(created) == 5  # 4 pages + 1 INDEX.md
        assert all(p.exists() for p in created)

    def test_written_index(
        self, registry: CompanyRegistry, manifest: CompanyManifest, tmp_path: Path
    ) -> None:
        gen = DocGenerator(registry, manifest)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        index_path = tmp_path / "docs" / "INDEX.md"
        assert index_path.exists()
        content = index_path.read_text(encoding="utf-8")
        assert "Alice CEO" in content
        assert "Onboarding" in content

    def test_department_no_roles(self, manifest: CompanyManifest) -> None:
        reg = CompanyRegistry(
            vision=VisionData(name="TestCo"),
            departments={"empty": DepartmentData(name="empty")},
        )
        gen = DocGenerator(reg, manifest)
        result = gen.generate()
        assert len(result.pages) == 1
        assert result.pages[0]["type"] == "department"
