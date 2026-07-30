"""Tests for the Executive Generator (Phase 3, Sprint 3).

Tests cover:
- ExecutiveGenerator.generate() producing packages for all executives
- Each artifact: executive.yaml, prompt.md, profile.md, knowledge.md, memory.md, agent.py
- Artifact content contains expected data from registry
- Validation
- Edge cases: empty registry, missing executive names
"""

from pathlib import Path

import pytest
import yaml

from ai_company.company.executive_generator import ExecutiveGenerator
from ai_company.models.company import (
    CompanyManifest,
    CompanyRegistry,
    Culture,
    ExecutiveEntry,
    Strategy,
    VisionData,
)

# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def single_exec_registry() -> CompanyRegistry:
    return CompanyRegistry(
        vision=VisionData(name="TestCo", company_name="TestCo Inc"),
        executives=[
            ExecutiveEntry(
                name="Alice CEO",
                title="Chief Executive Officer",
                bio="20+ years in enterprise SaaS.",
                department="executive",
                responsibilities=["Set vision", "Lead exec team", "Board relations"],
                kpis=["Revenue Growth", "Market Share"],
                budget_authority=5_000_000,
                direct_reports=["Bob CTO", "Carol CFO"],
                reports_to="Board of Directors",
                status="active",
                start_date="2023-01-15",
                email="alice@testco.io",
            ),
            ExecutiveEntry(
                name="Bob CTO",
                title="Chief Technology Officer",
                bio="PhD in CS, former VP Engineering.",
                department="engineering",
                responsibilities=["Tech vision", "Architecture"],
                kpis=["System Uptime", "Deploy Frequency"],
                budget_authority=2_000_000,
                direct_reports=["Engineering Managers"],
                reports_to="Alice CEO",
                status="active",
                start_date="2023-03-01",
                email="bob@testco.io",
            ),
        ],
        strategy=Strategy(
            name="Growth",
            description="Expand market presence through AI-native features.",
            objectives=["Launch v2", "Enterprise partnerships"],
        ),
        culture=Culture(
            values=["Innovation", "Transparency", "Excellence"],
        ),
    )


@pytest.fixture
def empty_exec_registry() -> CompanyRegistry:
    return CompanyRegistry(
        vision=VisionData(name="EmptyCo"),
    )


@pytest.fixture
def manifest() -> CompanyManifest:
    return CompanyManifest(
        name="TestCo Inc",
        company_name="TestCo Inc",
        description="A test company",
    )


# =========================================================================
# Tests
# =========================================================================


class TestExecutiveGenerator:
    def test_generate_with_executives(
        self, single_exec_registry: CompanyRegistry
    ) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        assert len(result.executables) == 2
        assert result.summary()["executives"] == 2

    def test_generate_with_empty_registry(
        self, empty_exec_registry: CompanyRegistry
    ) -> None:
        gen = ExecutiveGenerator(empty_exec_registry)
        result = gen.generate()
        assert len(result.executables) == 0

    def test_each_package_has_all_artifacts(
        self, single_exec_registry: CompanyRegistry
    ) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        for pkg in result.executables:
            assert "slug" in pkg
            assert "yaml" in pkg
            assert "prompt_md" in pkg
            assert "profile_md" in pkg
            assert "knowledge_md" in pkg
            assert "memory_md" in pkg
            assert "agent_py" in pkg

    def test_yaml_contains_all_fields(
        self, single_exec_registry: CompanyRegistry
    ) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        pkg = result.executables[0]
        y = pkg["yaml"]
        assert y["name"] == "Alice CEO"
        assert y["title"] == "Chief Executive Officer"
        assert y["department"] == "executive"
        assert len(y["responsibilities"]) == 3
        assert len(y["kpis"]) == 2
        assert y["budget_authority"] == 5_000_000
        assert len(y["direct_reports"]) == 2
        assert y["reports_to"] == "Board of Directors"
        assert y["status"] == "active"
        assert y["start_date"] == "2023-01-15"
        assert "agent_config" in y
        assert y["agent_config"]["model"] == "gpt-4o"

    def test_prompt_contains_executive_name(
        self, single_exec_registry: CompanyRegistry
    ) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        alice = next(p for p in result.executables if p["name"] == "Alice CEO")
        assert "Alice CEO" in alice["prompt_md"]
        assert "Chief Executive Officer" in alice["prompt_md"]
        assert "TestCo Inc" in alice["prompt_md"]

    def test_prompt_contains_bio_and_responsibilities(
        self, single_exec_registry: CompanyRegistry
    ) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        alice = next(p for p in result.executables if p["name"] == "Alice CEO")
        assert "20+ years in enterprise SaaS" in alice["prompt_md"]
        assert "Set vision" in alice["prompt_md"]

    def test_kpis_in_prompt(self, single_exec_registry: CompanyRegistry) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        alice = next(p for p in result.executables if p["name"] == "Alice CEO")
        assert "Revenue Growth" in alice["prompt_md"]
        assert "Market Share" in alice["prompt_md"]

    def test_profile_contains_bio(self, single_exec_registry: CompanyRegistry) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        alice = next(p for p in result.executables if p["name"] == "Alice CEO")
        assert "20+ years in enterprise SaaS" in alice["profile_md"]
        assert "Set vision" in alice["profile_md"]
        assert "Lead exec team" in alice["profile_md"]

    def test_knowledge_contains_domain_expertise(
        self, single_exec_registry: CompanyRegistry
    ) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        alice = next(p for p in result.executables if p["name"] == "Alice CEO")
        assert "Strategic leadership" in alice["knowledge_md"]
        assert "Corporate governance" in alice["knowledge_md"]
        assert "Budget Authority" in alice["knowledge_md"]
        assert "$5,000,000" in alice["knowledge_md"]
        assert "Innovation" in alice["knowledge_md"]
        assert "Transparency" in alice["knowledge_md"]
        assert "Expand market presence" in alice["knowledge_md"]

    def test_cto_knowledge_has_technical_expertise(
        self, single_exec_registry: CompanyRegistry
    ) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        bob = next(p for p in result.executables if p["name"] == "Bob CTO")
        assert "Software architecture" in bob["knowledge_md"]
        assert "AI/ML platform" in bob["knowledge_md"]
        assert "R&D portfolio" in bob["knowledge_md"]

    def test_memory_contains_role_and_company(
        self, single_exec_registry: CompanyRegistry
    ) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        alice = next(p for p in result.executables if p["name"] == "Alice CEO")
        assert "Chief Executive Officer" in alice["memory_md"]
        assert "TestCo Inc" in alice["memory_md"]
        assert "2023-01-15" in alice["memory_md"]

    def test_agent_py_contains_class(
        self, single_exec_registry: CompanyRegistry
    ) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        alice = next(p for p in result.executables if p["name"] == "Alice CEO")
        assert "class AliceCEOAgent" in alice["agent_py"]
        assert "Agent wrapper for Alice CEO" in alice["agent_py"]
        assert "gpt-4o" in alice["agent_py"]
        assert "registry-read" in alice["agent_py"]

    def test_agent_py_for_cto(self, single_exec_registry: CompanyRegistry) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        bob = next(p for p in result.executables if p["name"] == "Bob CTO")
        assert "class BobCTOAgent" in bob["agent_py"]
        assert "Agent wrapper for Bob CTO" in bob["agent_py"]

    def test_validate_valid(self, single_exec_registry: CompanyRegistry) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        errors = gen.validate()
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_validate_empty(self, empty_exec_registry: CompanyRegistry) -> None:
        gen = ExecutiveGenerator(empty_exec_registry)
        errors = gen.validate()
        assert len(errors) > 0, "Expected validation errors"

    def test_write_artifacts(
        self, single_exec_registry: CompanyRegistry, tmp_path: Path
    ) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        created = gen.write_artifacts(result, tmp_path)
        assert len(created) == 12  # 2 executives * 6 files each
        assert all(p.exists() for p in created)

    def test_written_yaml_is_valid(
        self, single_exec_registry: CompanyRegistry, tmp_path: Path
    ) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        yaml_path = tmp_path / "executives" / "alice_ceo" / "executive.yaml"
        assert yaml_path.exists()
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert data["name"] == "Alice CEO"
        assert data["title"] == "Chief Executive Officer"

    def test_written_prompt_exists(
        self, single_exec_registry: CompanyRegistry, tmp_path: Path
    ) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        prompt_path = tmp_path / "executives" / "alice_ceo" / "prompt.md"
        assert prompt_path.exists()
        assert "Alice CEO" in prompt_path.read_text(encoding="utf-8")

    def test_written_profile_exists(
        self, single_exec_registry: CompanyRegistry, tmp_path: Path
    ) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        profile_path = tmp_path / "executives" / "alice_ceo" / "profile.md"
        assert profile_path.exists()
        assert "Set vision" in profile_path.read_text(encoding="utf-8")

    def test_written_knowledge_exists(
        self, single_exec_registry: CompanyRegistry, tmp_path: Path
    ) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        knowledge_path = tmp_path / "executives" / "alice_ceo" / "knowledge.md"
        assert knowledge_path.exists()
        assert "Strategic leadership" in knowledge_path.read_text(encoding="utf-8")

    def test_written_memory_exists(
        self, single_exec_registry: CompanyRegistry, tmp_path: Path
    ) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        memory_path = tmp_path / "executives" / "alice_ceo" / "memory.md"
        assert memory_path.exists()

    def test_written_agent_py_exists(
        self, single_exec_registry: CompanyRegistry, tmp_path: Path
    ) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        agent_path = tmp_path / "executives" / "alice_ceo" / "agent.py"
        assert agent_path.exists()
        assert "class AliceCEOAgent" in agent_path.read_text(encoding="utf-8")

    def test_report_to_in_knowledge(
        self, single_exec_registry: CompanyRegistry
    ) -> None:
        gen = ExecutiveGenerator(single_exec_registry)
        result = gen.generate()
        bob = next(p for p in result.executables if p["name"] == "Bob CTO")
        assert "**Reports To:** Alice CEO" in bob["knowledge_md"]
