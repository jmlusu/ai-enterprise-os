"""Tests for the Prompt Library Generator (Phase 7, Sprint 3)."""

from pathlib import Path

import pytest

from ai_company.company.prompt_generator import PromptLibraryGenerator
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
            ExecutiveEntry(name="Alice CEO", title="CEO"),
        ],
        departments={
            "engineering": DepartmentData(
                name="engineering",
                roles=[Role(title="Engineer")],
            ),
        },
        specialists=[
            SpecialistEntry(name="Bob", expertise="ML"),
        ],
        strategy=Strategy(name="Growth", description="Grow", objectives=["Launch"]),
        culture=Culture(values=["Innovation"]),
    )


@pytest.fixture
def empty_registry() -> CompanyRegistry:
    return CompanyRegistry(vision=VisionData(name="EmptyCo"))


class TestPromptLibraryGenerator:
    def test_generate_with_entities(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = PromptLibraryGenerator(registry, manifest)
        result = gen.generate()
        assert result.summary()["prompts"] == 3  # exec + dept + specialist

    def test_generate_with_empty_registry(
        self, empty_registry: CompanyRegistry
    ) -> None:
        gen = PromptLibraryGenerator(empty_registry)
        result = gen.generate()
        assert len(result.prompts) == 0

    def test_prompts_have_types(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = PromptLibraryGenerator(registry, manifest)
        result = gen.generate()
        types = {p["type"] for p in result.prompts}
        assert "executive" in types
        assert "department" in types
        assert "specialist" in types

    def test_prompt_text_contains_name(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = PromptLibraryGenerator(registry, manifest)
        result = gen.generate()
        alice = next(p for p in result.prompts if p["name"] == "Alice CEO")
        assert "Alice CEO" in alice["prompt_text"]

    def test_validate_valid(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = PromptLibraryGenerator(registry, manifest)
        errors = gen.validate()
        assert errors == []

    def test_validate_empty(self, empty_registry: CompanyRegistry) -> None:
        gen = PromptLibraryGenerator(empty_registry)
        errors = gen.validate()
        assert len(errors) > 0

    def test_write_artifacts(
        self, registry: CompanyRegistry, manifest: CompanyManifest, tmp_path: Path
    ) -> None:
        gen = PromptLibraryGenerator(registry, manifest)
        result = gen.generate()
        created = gen.write_artifacts(result, tmp_path)
        assert len(created) == 4  # 3 prompts + 1 INDEX.md
        assert all(p.exists() for p in created)

    def test_written_index_exists(
        self, registry: CompanyRegistry, manifest: CompanyManifest, tmp_path: Path
    ) -> None:
        gen = PromptLibraryGenerator(registry, manifest)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        index_path = tmp_path / "prompts" / "INDEX.md"
        assert index_path.exists()
        content = index_path.read_text(encoding="utf-8")
        assert "Alice CEO" in content
