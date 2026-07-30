"""Tests for the Specialist Generator (Phase 5, Sprint 3)."""

from pathlib import Path

import pytest
import yaml

from ai_company.company.specialist_generator import SpecialistGenerator
from ai_company.models.company import (
    CompanyManifest,
    CompanyRegistry,
    SpecialistEntry,
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
        specialists=[
            SpecialistEntry(name="Bob", expertise="Machine Learning"),
            SpecialistEntry(name="Carol", expertise="Data Engineering"),
        ],
    )


@pytest.fixture
def empty_registry() -> CompanyRegistry:
    return CompanyRegistry(vision=VisionData(name="EmptyCo"))


class TestSpecialistGenerator:
    def test_generate_with_specialists(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = SpecialistGenerator(registry, manifest)
        result = gen.generate()
        assert len(result.specialists) == 2
        assert result.summary()["specialists"] == 2

    def test_generate_with_empty_registry(
        self, empty_registry: CompanyRegistry
    ) -> None:
        gen = SpecialistGenerator(empty_registry)
        result = gen.generate()
        assert len(result.specialists) == 0

    def test_each_package_has_all_artifacts(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = SpecialistGenerator(registry, manifest)
        result = gen.generate()
        for pkg in result.specialists:
            assert "slug" in pkg
            assert "yaml" in pkg
            assert "prompt_md" in pkg
            assert "profile_md" in pkg
            assert "memory_md" in pkg

    def test_yaml_contains_name_and_expertise(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = SpecialistGenerator(registry, manifest)
        result = gen.generate()
        bob = next(p for p in result.specialists if p["name"] == "Bob")
        assert bob["yaml"]["name"] == "Bob"
        assert bob["yaml"]["expertise"] == "Machine Learning"

    def test_prompt_contains_specialist_name(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = SpecialistGenerator(registry, manifest)
        result = gen.generate()
        bob = next(p for p in result.specialists if p["name"] == "Bob")
        assert "Bob" in bob["prompt_md"]

    def test_profile_contains_expertise(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = SpecialistGenerator(registry, manifest)
        result = gen.generate()
        bob = next(p for p in result.specialists if p["name"] == "Bob")
        assert "Machine Learning" in bob["profile_md"]

    def test_memory_contains_company(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = SpecialistGenerator(registry, manifest)
        result = gen.generate()
        carol = next(p for p in result.specialists if p["name"] == "Carol")
        assert "TestCo Inc" in carol["memory_md"]

    def test_validate_valid(
        self, registry: CompanyRegistry, manifest: CompanyManifest
    ) -> None:
        gen = SpecialistGenerator(registry, manifest)
        errors = gen.validate()
        assert errors == []

    def test_validate_empty(self, empty_registry: CompanyRegistry) -> None:
        gen = SpecialistGenerator(empty_registry)
        errors = gen.validate()
        assert len(errors) > 0

    def test_write_artifacts(
        self, registry: CompanyRegistry, manifest: CompanyManifest, tmp_path: Path
    ) -> None:
        gen = SpecialistGenerator(registry, manifest)
        result = gen.generate()
        created = gen.write_artifacts(result, tmp_path)
        assert len(created) == 8  # 2 specialists * 4 files each
        assert all(p.exists() for p in created)

    def test_written_yaml_is_valid(
        self, registry: CompanyRegistry, manifest: CompanyManifest, tmp_path: Path
    ) -> None:
        gen = SpecialistGenerator(registry, manifest)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        yaml_path = tmp_path / "specialists" / "bob" / "specialist.yaml"
        assert yaml_path.exists()
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert data["name"] == "Bob"
        assert data["expertise"] == "Machine Learning"

    def test_written_prompt_exists(
        self, registry: CompanyRegistry, manifest: CompanyManifest, tmp_path: Path
    ) -> None:
        gen = SpecialistGenerator(registry, manifest)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        prompt_path = tmp_path / "specialists" / "bob" / "prompt.md"
        assert prompt_path.exists()

    def test_written_profile_exists(
        self, registry: CompanyRegistry, manifest: CompanyManifest, tmp_path: Path
    ) -> None:
        gen = SpecialistGenerator(registry, manifest)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        profile_path = tmp_path / "specialists" / "bob" / "profile.md"
        assert profile_path.exists()
        assert "Machine Learning" in profile_path.read_text(encoding="utf-8")

    def test_written_memory_exists(
        self, registry: CompanyRegistry, manifest: CompanyManifest, tmp_path: Path
    ) -> None:
        gen = SpecialistGenerator(registry, manifest)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        memory_path = tmp_path / "specialists" / "carol" / "memory.md"
        assert memory_path.exists()
