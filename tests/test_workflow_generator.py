"""Tests for the Workflow Generator (Phase 6, Sprint 3)."""

from pathlib import Path

import pytest
import yaml

from ai_company.company.workflow_generator import WorkflowGenerator
from ai_company.models.company import CompanyRegistry, VisionData, WorkflowEntry


@pytest.fixture
def registry() -> CompanyRegistry:
    return CompanyRegistry(
        vision=VisionData(name="TestCo"),
        workflows=[
            WorkflowEntry(
                name="Onboarding",
                description="New hire onboarding flow",
                steps=[
                    "Send welcome email",
                    "Schedule orientation",
                    "Assign mentor",
                    "Set up accounts",
                ],
            ),
            WorkflowEntry(
                name="Deploy",
                description="Release deployment process",
                steps=[
                    "Code review",
                    "Run tests",
                    "Build artifact",
                    "Deploy to staging",
                    "Deploy to production",
                ],
            ),
        ],
    )


@pytest.fixture
def empty_registry() -> CompanyRegistry:
    return CompanyRegistry(vision=VisionData(name="EmptyCo"))


class TestWorkflowGenerator:
    def test_generate_with_workflows(self, registry: CompanyRegistry) -> None:
        gen = WorkflowGenerator(registry)
        result = gen.generate()
        assert len(result.workflows) == 2
        assert result.summary()["workflows"] == 2

    def test_generate_with_empty_registry(
        self, empty_registry: CompanyRegistry
    ) -> None:
        gen = WorkflowGenerator(empty_registry)
        result = gen.generate()
        assert len(result.workflows) == 0

    def test_each_package_has_all_artifacts(self, registry: CompanyRegistry) -> None:
        gen = WorkflowGenerator(registry)
        result = gen.generate()
        for pkg in result.workflows:
            assert "slug" in pkg
            assert "yaml" in pkg
            assert "workflow_md" in pkg

    def test_yaml_contains_name_and_steps(self, registry: CompanyRegistry) -> None:
        gen = WorkflowGenerator(registry)
        result = gen.generate()
        onboarding = next(p for p in result.workflows if p["name"] == "Onboarding")
        assert onboarding["yaml"]["name"] == "Onboarding"
        assert len(onboarding["yaml"]["steps"]) == 4

    def test_workflow_md_contains_steps(self, registry: CompanyRegistry) -> None:
        gen = WorkflowGenerator(registry)
        result = gen.generate()
        onboarding = next(p for p in result.workflows if p["name"] == "Onboarding")
        assert "Send welcome email" in onboarding["workflow_md"]
        assert "Assign mentor" in onboarding["workflow_md"]

    def test_workflow_md_contains_description(self, registry: CompanyRegistry) -> None:
        gen = WorkflowGenerator(registry)
        result = gen.generate()
        deploy = next(p for p in result.workflows if p["name"] == "Deploy")
        assert "Release deployment process" in deploy["workflow_md"]

    def test_validate_valid(self, registry: CompanyRegistry) -> None:
        gen = WorkflowGenerator(registry)
        errors = gen.validate()
        assert errors == []

    def test_validate_empty(self, empty_registry: CompanyRegistry) -> None:
        gen = WorkflowGenerator(empty_registry)
        errors = gen.validate()
        assert len(errors) > 0

    def test_write_artifacts(self, registry: CompanyRegistry, tmp_path: Path) -> None:
        gen = WorkflowGenerator(registry)
        result = gen.generate()
        created = gen.write_artifacts(result, tmp_path)
        assert len(created) == 4  # 2 workflows * 2 files each
        assert all(p.exists() for p in created)

    def test_written_yaml_is_valid(
        self, registry: CompanyRegistry, tmp_path: Path
    ) -> None:
        gen = WorkflowGenerator(registry)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        yaml_path = tmp_path / "workflows" / "onboarding" / "workflow.yaml"
        assert yaml_path.exists()
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert data["name"] == "Onboarding"

    def test_written_doc_exists(
        self, registry: CompanyRegistry, tmp_path: Path
    ) -> None:
        gen = WorkflowGenerator(registry)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        doc_path = tmp_path / "workflows" / "deploy" / "workflow.md"
        assert doc_path.exists()
        assert "Deploy" in doc_path.read_text(encoding="utf-8")
