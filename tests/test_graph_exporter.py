"""Tests for the Graph Export Enhancement (Phase 9, Sprint 3)."""

from pathlib import Path

import pytest

from ai_company.company.graph_exporter import GraphExporter
from ai_company.models.company import (
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
def registry() -> CompanyRegistry:
    return CompanyRegistry(
        vision=VisionData(name="TestCo", company_name="TestCo Inc"),
        executives=[
            ExecutiveEntry(name="CEO Alice", title="CEO", department="executive"),
            ExecutiveEntry(
                name="CTO Bob",
                title="CTO",
                department="engineering",
                reports_to="CEO Alice",
            ),
        ],
        departments={
            "executive": DepartmentData(name="executive"),
            "engineering": DepartmentData(
                name="engineering", roles=[Role(title="Engineer")]
            ),
        },
        specialists=[SpecialistEntry(name="Charlie", expertise="Data")],
        workflows=[
            WorkflowEntry(name="Onboarding", steps=["Step 1", "Step 2"]),
        ],
        strategy=Strategy(name="Growth", description="Grow", objectives=["Launch"]),
        culture=Culture(values=["Innovation"]),
    )


@pytest.fixture
def empty_registry() -> CompanyRegistry:
    return CompanyRegistry(vision=VisionData(name="EmptyCo"))


class TestGraphExporter:
    def test_generate_mermaid(self, registry: CompanyRegistry) -> None:
        exporter = GraphExporter(registry)
        result = exporter.generate()
        assert "flowchart TD" in result.mermaid
        assert "CEO_Alice" in result.mermaid
        assert "CTO_Bob" in result.mermaid
        assert "dept_engineering" in result.mermaid

    def test_generate_edges(self, registry: CompanyRegistry) -> None:
        exporter = GraphExporter(registry)
        result = exporter.generate()
        # Executive → department edge
        assert "CEO_Alice --> dept_executive" in result.mermaid
        # Reports-to edge
        assert "CTO_Bob --> CEO_Alice" in result.mermaid

    def test_generate_workflows(self, registry: CompanyRegistry) -> None:
        exporter = GraphExporter(registry)
        result = exporter.generate()
        assert "wf_Onboarding" in result.mermaid

    def test_generate_empty(self, empty_registry: CompanyRegistry) -> None:
        exporter = GraphExporter(empty_registry)
        result = exporter.generate()
        assert "flowchart TD" in result.mermaid

    def test_validate_valid(self, registry: CompanyRegistry) -> None:
        exporter = GraphExporter(registry)
        errors = exporter.validate()
        assert errors == []

    def test_validate_empty(self, empty_registry: CompanyRegistry) -> None:
        exporter = GraphExporter(empty_registry)
        errors = exporter.validate()
        assert len(errors) > 0

    def test_write_artifacts(self, registry: CompanyRegistry, tmp_path: Path) -> None:
        exporter = GraphExporter(registry)
        result = exporter.generate()
        created = exporter.write_artifacts(result, tmp_path)
        assert len(created) == 2  # mermaid + json
        assert all(p.exists() for p in created)

    def test_written_mermaid_content(
        self, registry: CompanyRegistry, tmp_path: Path
    ) -> None:
        exporter = GraphExporter(registry)
        result = exporter.generate()
        exporter.write_artifacts(result, tmp_path)
        mermaid_path = tmp_path / "graph" / "org_chart.mmd"
        content = mermaid_path.read_text(encoding="utf-8")
        assert "CEO_Alice" in content

    def test_written_json_content(
        self, registry: CompanyRegistry, tmp_path: Path
    ) -> None:
        exporter = GraphExporter(registry)
        result = exporter.generate()
        exporter.write_artifacts(result, tmp_path)
        json_path = tmp_path / "graph" / "graph_enriched.json"
        content = json_path.read_text(encoding="utf-8")
        assert "CEO Alice" in content
        assert "engineering" in content
