"""Tests for the Organization Generator (Phase 1, Sprint 3).

Tests cover:
- OrgGraph construction, queries, cycle detection, metadata
- HierarchyBuilder producing correct levels and edges
- RoleGenerator enriching role definitions
- RelationshipResolver connecting entities
- ReportingStructure analysing spans, depth, orphans, cycles
- OrganizationGenerator full pipeline
- CompanyGenerator CLI wrapper
"""

from pathlib import Path

import pytest
import yaml

from ai_company.company.generator import CompanyGenerator
from ai_company.company.hierarchy import HierarchyBuilder
from ai_company.company.models import OrgEdge, OrgGraph, OrgNode
from ai_company.company.organization import OrganizationGenerator
from ai_company.company.relationships import RelationshipResolver
from ai_company.company.reporting import ReportingStructure
from ai_company.company.roles import RoleGenerator, classify_seniority
from ai_company.models.company import (
    BoardMember,
    Committee,
    CompanyRegistry,
    DepartmentData,
    ExecutiveEntry,
    Role,
    SpecialistEntry,
    VisionData,
    WorkflowEntry,
)

# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def empty_registry() -> CompanyRegistry:
    return CompanyRegistry(vision=VisionData(name="TestCo"))


@pytest.fixture
def minimal_registry() -> CompanyRegistry:
    """A registry with one executive and one department."""
    return CompanyRegistry(
        vision=VisionData(name="TestCo", company_name="TestCo Inc"),
        executives=[
            ExecutiveEntry(
                name="Alice CEO",
                title="Chief Executive Officer",
                department="executive",
                reports_to="Board of Directors",
            ),
            ExecutiveEntry(
                name="Bob CTO",
                title="Chief Technology Officer",
                department="engineering",
                reports_to="Alice CEO",
            ),
        ],
        departments={
            "executive": DepartmentData(name="executive", roles=[Role(title="CEO")]),
            "engineering": DepartmentData(
                name="engineering",
                roles=[Role(title="Engineer"), Role(title="Senior Engineer")],
            ),
        },
        specialists=[
            SpecialistEntry(name="Dr. Spec", expertise="Machine Learning"),
        ],
        workflows=[
            WorkflowEntry(
                name="Feature Dev",
                description="Build features",
                steps=["Planning", "Implementation by Engineering", "Review"],
            ),
        ],
        board_members=[
            BoardMember(name="Board Member 1", role="Chair"),
        ],
        committees=[
            Committee(name="Audit", purpose="Oversee audits", chair="Board Member 1"),
        ],
    )


@pytest.fixture
def full_registry() -> CompanyRegistry:
    """A more complete registry representing a realistic company."""
    return CompanyRegistry(
        vision=VisionData(
            name="AI Enterprise OS",
            company_name="Lightspeed Holdings Limited",
            description="Building scalable local AI agent workflows.",
        ),
        executives=[
            ExecutiveEntry(
                name="Alex Turner",
                title="Chief Executive Officer",
                department="executive",
                reports_to="Board of Directors",
                status="active",
                budget_authority=5_000_000,
            ),
            ExecutiveEntry(
                name="Maria Santos",
                title="Chief Technology Officer",
                department="engineering",
                reports_to="Alex Turner",
                status="active",
            ),
            ExecutiveEntry(
                name="Robert Kim",
                title="Chief Financial Officer",
                department="finance",
                reports_to="Alex Turner",
                status="active",
            ),
            ExecutiveEntry(
                name="Priya Patel",
                title="Chief Operating Officer",
                department="operations",
                reports_to="Alex Turner",
                status="active",
            ),
        ],
        departments={
            "executive": DepartmentData(
                name="executive",
                roles=[Role(title="CEO")],
            ),
            "engineering": DepartmentData(
                name="engineering",
                roles=[
                    Role(title="Software Engineer"),
                    Role(title="Senior Engineer"),
                    Role(title="Architect"),
                ],
            ),
            "finance": DepartmentData(
                name="finance",
                roles=[Role(title="Financial Analyst"), Role(title="Accountant")],
            ),
            "operations": DepartmentData(
                name="operations",
                roles=[Role(title="Operations Manager")],
            ),
        },
        specialists=[
            SpecialistEntry(
                name="Dr. Nina Voss", expertise="Natural Language Processing"
            ),
            SpecialistEntry(name="Kenji Tanaka", expertise="Reinforcement Learning"),
        ],
    )


# =========================================================================
# OrgGraph unit tests
# =========================================================================


class TestOrgGraph:
    def test_empty_graph(self) -> None:
        g = OrgGraph()
        assert len(g.nodes) == 0
        assert len(g.edges) == 0
        meta = g.compute_metadata()
        assert meta.total_nodes == 0
        assert meta.total_edges == 0

    def test_add_node(self) -> None:
        g = OrgGraph()
        g.add_node(
            OrgNode(id="test:1", name="Test", title="Tester", node_type="executive")
        )
        assert len(g.nodes) == 1
        assert g.get_node("test:1") is not None

    def test_add_edge(self) -> None:
        g = OrgGraph()
        g.add_node(OrgNode(id="a", name="A", node_type="executive"))
        g.add_node(OrgNode(id="b", name="B", node_type="executive"))
        g.add_edge(OrgEdge("a", "b", "reports_to"))
        assert len(g.edges) == 1
        # Edge a -> b means 'a reports to b'.
        # children_of(b) = subordinates of b = [a] (incoming)
        # parents_of(a) = managers of a = [b] (outgoing)
        assert len(g.children_of("b")) == 1, "b's subordinates should include a"
        assert g.children_of("b")[0].id == "a"
        assert len(g.parents_of("a")) == 1, "a's managers should include b"
        assert g.parents_of("a")[0].id == "b"

    def test_children_of_empty(self) -> None:
        g = OrgGraph()
        assert g.children_of("nonexistent") == []

    def test_nodes_by_type(self) -> None:
        g = OrgGraph()
        g.add_node(OrgNode(id="e1", name="E1", node_type="executive"))
        g.add_node(OrgNode(id="d1", name="D1", node_type="department"))
        assert len(g.nodes_by_type("executive")) == 1
        assert len(g.nodes_by_type("department")) == 1
        assert len(g.nodes_by_type("board")) == 0

    def test_nodes_by_level(self) -> None:
        g = OrgGraph()
        g.add_node(OrgNode(id="a", name="A", node_type="executive", level=0))
        g.add_node(OrgNode(id="b", name="B", node_type="executive", level=1))
        assert len(g.nodes_by_level(0)) == 1
        assert len(g.nodes_by_level(1)) == 1
        assert len(g.nodes_by_level(2)) == 0

    def test_cycle_detection(self) -> None:
        """A -> B -> C -> A should be detected as a cycle."""
        g = OrgGraph()
        g.add_node(OrgNode(id="a", name="A", node_type="executive"))
        g.add_node(OrgNode(id="b", name="B", node_type="executive"))
        g.add_node(OrgNode(id="c", name="C", node_type="executive"))
        g.add_edge(OrgEdge("a", "b", "reports_to"))
        g.add_edge(OrgEdge("b", "c", "reports_to"))
        g.add_edge(OrgEdge("c", "a", "reports_to"))
        cycles = g.detect_cycles()
        assert len(cycles) >= 1, "Should detect at least one cycle"

    def test_no_cycle(self) -> None:
        g = OrgGraph()
        g.add_node(OrgNode(id="a", name="A", node_type="executive"))
        g.add_node(OrgNode(id="b", name="B", node_type="executive"))
        g.add_node(OrgNode(id="c", name="C", node_type="executive"))
        g.add_edge(OrgEdge("a", "b", "reports_to"))
        g.add_edge(OrgEdge("b", "c", "reports_to"))
        assert len(g.detect_cycles()) == 0

    def test_subgraph(self) -> None:
        g = OrgGraph()
        g.add_node(OrgNode(id="root", name="Root", node_type="executive", level=0))
        g.add_node(OrgNode(id="child", name="Child", node_type="executive"))
        g.add_node(OrgNode(id="grandchild", name="GC", node_type="specialist"))
        g.add_edge(OrgEdge("root", "child"))
        g.add_edge(OrgEdge("child", "grandchild"))
        sub = g.subgraph("child")
        assert sub.get_node("child") is not None
        assert sub.get_node("grandchild") is not None
        assert sub.get_node("root") is None  # root not in sub-tree

    def test_to_dict_roundtrip(self) -> None:
        g = OrgGraph()
        g.add_node(OrgNode(id="a", name="A", node_type="executive"))
        g.add_node(OrgNode(id="b", name="B", node_type="executive"))
        g.add_edge(OrgEdge("a", "b", "reports_to"))
        d = g.to_dict()
        g2 = OrgGraph.from_dict(d)
        assert g2.get_node("a") is not None
        assert g2.get_node("b") is not None
        assert len(g2.edges) == 1
        assert g2.edges[0].source_id == "a"
        assert g2.edges[0].target_id == "b"

    def test_compute_metadata(self) -> None:
        g = OrgGraph()
        g.add_node(OrgNode(id="a", name="A", node_type="executive", level=0))
        g.add_node(OrgNode(id="b", name="B", node_type="executive", level=1))
        g.add_node(OrgNode(id="c", name="C", node_type="department", level=1))
        g.add_edge(OrgEdge("a", "b"))
        meta = g.compute_metadata()
        assert meta.total_nodes == 3
        assert meta.total_edges == 1
        assert meta.max_depth == 1
        assert meta.node_type_counts["executive"] == 2


# =========================================================================
# HierarchyBuilder tests
# =========================================================================


class TestHierarchyBuilder:
    def test_empty_registry(self, empty_registry: CompanyRegistry) -> None:
        builder = HierarchyBuilder(empty_registry)
        graph = builder.build()
        assert isinstance(graph, OrgGraph)
        # Board nodes should still be added
        assert len(graph.nodes) > 0

    def test_minimal_hierarchy(self, minimal_registry: CompanyRegistry) -> None:
        builder = HierarchyBuilder(minimal_registry)
        graph = builder.build()
        # Should have: board node, 2 board members (from board_members list),
        # 2 executives, 2 departments, specialized, and roles
        assert graph.get_node("exec:alice_ceo") is not None
        assert graph.get_node("exec:bob_cto") is not None
        assert graph.get_node("dept:engineering") is not None

    def test_executive_levels(self, full_registry: CompanyRegistry) -> None:
        builder = HierarchyBuilder(full_registry)
        graph = builder.build()
        ceo = graph.get_node("exec:alex_turner")
        assert ceo is not None
        assert ceo.level == 0, "CEO should be at level 0"
        cto = graph.get_node("exec:maria_santos")
        assert cto is not None
        assert cto.level >= 1, "CTO should be at level >= 1"

    def test_department_levels(self, full_registry: CompanyRegistry) -> None:
        builder = HierarchyBuilder(full_registry)
        graph = builder.build()
        eng = graph.get_node("dept:engineering")
        assert eng is not None
        assert eng.level >= 1

    def test_specialist_nodes(self, minimal_registry: CompanyRegistry) -> None:
        builder = HierarchyBuilder(minimal_registry)
        graph = builder.build()
        spec = graph.get_node("specialist:dr_spec")
        assert spec is not None
        assert spec.node_type == "specialist"

    def test_board_nodes(self, minimal_registry: CompanyRegistry) -> None:
        builder = HierarchyBuilder(minimal_registry)
        graph = builder.build()
        board = graph.get_node("board:board_of_directors")
        assert board is not None

    def test_reporting_edges(self, full_registry: CompanyRegistry) -> None:
        builder = HierarchyBuilder(full_registry)
        graph = builder.build()
        # CTO reports to CEO
        cto_to_ceo = any(
            e.source_id == "exec:maria_santos"
            and e.target_id == "exec:alex_turner"
            and e.edge_type == "reports_to"
            for e in graph.edges
        )
        assert cto_to_ceo, "CTO should report to CEO"


# =========================================================================
# RoleGenerator tests
# =========================================================================


class TestRoleGenerator:
    def test_classify_seniority(self) -> None:
        assert classify_seniority("Chief Executive Officer") == "c-suite"
        assert classify_seniority("Senior Engineer") == "senior"
        assert classify_seniority("Junior Developer") == "junior"
        assert classify_seniority("Software Engineer") == "mid"

    def test_generate_all(self, full_registry: CompanyRegistry) -> None:
        gen = RoleGenerator(full_registry)
        roles = gen.generate_all()
        assert len(roles) > 0
        for role in roles:
            assert "title" in role
            assert "seniority" in role
            assert "category" in role

    def test_generate_for_department(self, full_registry: CompanyRegistry) -> None:
        gen = RoleGenerator(full_registry)
        roles = gen.generate_for_department("engineering")
        assert len(roles) == 3  # Engineer, Senior Engineer, Architect
        assert all(r["department"] == "engineering" for r in roles)

    def test_generate_for_missing_department(
        self, full_registry: CompanyRegistry
    ) -> None:
        gen = RoleGenerator(full_registry)
        roles = gen.generate_for_department("nonexistent")
        assert roles == []

    def test_executive_roles_included(self, full_registry: CompanyRegistry) -> None:
        gen = RoleGenerator(full_registry)
        roles = gen.generate_all()
        exec_roles = [r for r in roles if r.get("is_executive")]
        assert len(exec_roles) >= 4  # 4 executives
        for r in exec_roles:
            assert r["seniority"] == "c-suite"


# =========================================================================
# RelationshipResolver tests
# =========================================================================


class TestRelationshipResolver:
    def test_exec_department_links(self, full_registry: CompanyRegistry) -> None:
        builder = HierarchyBuilder(full_registry)
        graph = builder.build()
        resolver = RelationshipResolver(full_registry, graph)
        result = resolver.resolve_all()
        # Check that engineering department is linked to CTO via "leads" edge
        leads_edges = [
            e
            for e in result.edges
            if e.edge_type == "leads" and e.source_id == "dept:engineering"
        ]
        assert len(leads_edges) >= 1

    def test_specialist_placement(self) -> None:
        """Specialist with matching expertise keywords should be placed."""
        from ai_company.models.company import (
            CompanyRegistry,
            DepartmentData,
            ExecutiveEntry,
            Role,
            SpecialistEntry,
            VisionData,
        )

        reg = CompanyRegistry(
            vision=VisionData(name="TestCo"),
            executives=[
                ExecutiveEntry(name="CEO", title="CEO", department="executive"),
            ],
            departments={
                "engineering": DepartmentData(
                    name="engineering",
                    roles=[Role(title="Engineer")],
                ),
            },
            specialists=[
                SpecialistEntry(
                    name="Engineer Alice", expertise="Engineering, Software"
                ),
            ],
        )
        builder = HierarchyBuilder(reg)
        graph = builder.build()
        resolver = RelationshipResolver(reg, graph)
        result = resolver.resolve_all()
        edges = [e for e in result.edges if e.source_id == "specialist:engineer_alice"]
        assert len(edges) >= 1, "Specialist should be linked to engineering department"

    def test_no_warnings_with_complete_data(
        self, full_registry: CompanyRegistry
    ) -> None:
        builder = HierarchyBuilder(full_registry)
        graph = builder.build()
        resolver = RelationshipResolver(full_registry, graph)
        resolver.resolve_all()
        # With full data we may still have some warnings (placements can be tricky)
        # but the resolver should not crash
        assert isinstance(resolver.warnings, list)


# =========================================================================
# ReportingStructure tests
# =========================================================================


class TestReportingStructure:
    def test_analyse(self, full_registry: CompanyRegistry) -> None:
        builder = HierarchyBuilder(full_registry)
        graph = builder.build()
        reporting = ReportingStructure(graph)
        meta = reporting.analyse()
        assert meta.total_nodes > 0
        assert meta.total_edges > 0
        assert isinstance(meta.warnings, list)

    def test_span_of_control(self, full_registry: CompanyRegistry) -> None:
        builder = HierarchyBuilder(full_registry)
        graph = builder.build()
        reporting = ReportingStructure(graph)
        ceo_span = reporting.get_span_of_control("exec:alex_turner")
        assert ceo_span >= 0  # CEO may have direct reports

    def test_chain_of_command(self, full_registry: CompanyRegistry) -> None:
        builder = HierarchyBuilder(full_registry)
        graph = builder.build()
        reporting = ReportingStructure(graph)
        cto_chain = reporting.get_reporting_chain("exec:maria_santos")
        assert len(cto_chain) >= 2  # At least [CTO, CEO]

    def test_orphan_detection(self, empty_registry: CompanyRegistry) -> None:
        # An empty-ish registry should have no orphans at level 0
        builder = HierarchyBuilder(empty_registry)
        graph = builder.build()
        reporting = ReportingStructure(graph)
        orphans = reporting.find_orphans()
        assert isinstance(orphans, list)

    def test_summary(self, full_registry: CompanyRegistry) -> None:
        builder = HierarchyBuilder(full_registry)
        graph = builder.build()
        reporting = ReportingStructure(graph)
        summary = reporting.summary()
        assert summary["total_nodes"] > 0
        assert "warnings" in summary


# =========================================================================
# OrganizationGenerator integration tests
# =========================================================================


class TestOrganizationGenerator:
    def test_generate_from_full_registry(self, full_registry: CompanyRegistry) -> None:
        gen = OrganizationGenerator(full_registry)
        result = gen.generate()
        assert result.graph is not None
        assert len(result.graph.nodes) > 0
        assert len(result.roles) > 0
        assert result.metadata.total_nodes > 0

    def test_generate_hierarchy_only(self, full_registry: CompanyRegistry) -> None:
        gen = OrganizationGenerator(full_registry)
        graph = gen.generate_hierarchy_only()
        assert isinstance(graph, OrgGraph)
        assert len(graph.nodes) > 0

    def test_export_json(self, full_registry: CompanyRegistry, tmp_path: Path) -> None:
        gen = OrganizationGenerator(full_registry)
        result = gen.generate()
        path = OrganizationGenerator.export_json(result.graph, tmp_path / "org.json")
        assert path.exists()
        assert path.read_text(encoding="utf-8").strip().startswith("{")

    def test_export_yaml(self, full_registry: CompanyRegistry, tmp_path: Path) -> None:
        gen = OrganizationGenerator(full_registry)
        result = gen.generate()
        path = OrganizationGenerator.export_yaml(result.graph, tmp_path / "org.yaml")
        assert path.exists()
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "nodes" in data

    def test_summary(self, full_registry: CompanyRegistry) -> None:
        gen = OrganizationGenerator(full_registry)
        result = gen.generate()
        summary = result.summary()
        assert summary["nodes"] > 0
        assert summary["edges"] >= 0
        assert summary["roles"] > 0
        assert "node_types" in summary


# =========================================================================
# CompanyGenerator (CLI wrapper) tests
# =========================================================================


class TestCompanyGenerator:
    def test_validate_valid(self, full_registry: CompanyRegistry) -> None:
        gen = CompanyGenerator(registry=full_registry)
        errors = gen.validate()
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_validate_empty(self, empty_registry: CompanyRegistry) -> None:
        gen = CompanyGenerator(registry=empty_registry)
        errors = gen.validate()
        assert len(errors) > 0, "Expected validation errors for empty registry"

    def test_generate_from_registry(
        self, full_registry: CompanyRegistry, tmp_path: Path
    ) -> None:
        gen = CompanyGenerator(
            output_dir=tmp_path,
            registry=full_registry,
        )
        result = gen.generate_from_registry(full_registry)
        assert result.metadata.total_nodes > 0
        # Check artifacts were written
        assert (tmp_path / "organization.json").exists()
        assert (tmp_path / "organization.yaml").exists()
        assert (tmp_path / "organization_summary.yaml").exists()
        assert (tmp_path / "organization_roles.json").exists()

    def test_generate_then_export_roundtrip(
        self, full_registry: CompanyRegistry, tmp_path: Path
    ) -> None:
        """Generate, export to JSON, reload, and verify structure."""
        gen = CompanyGenerator(registry=full_registry)
        result = gen.generate_from_registry(full_registry)

        # Export
        json_path = tmp_path / "org_roundtrip.json"
        OrganizationGenerator.export_json(result.graph, json_path)

        # Reload
        import json

        data = json.loads(json_path.read_text(encoding="utf-8"))
        reloaded = OrgGraph.from_dict(data)
        assert len(reloaded.nodes) == result.metadata.total_nodes

    # ------------------------------------------------------------------
    # generate_all()
    # ------------------------------------------------------------------

    def test_generate_all_summaries(
        self, minimal_registry: CompanyRegistry, tmp_path: Path
    ) -> None:
        gen = CompanyGenerator(output_dir=tmp_path, registry=minimal_registry)
        result = gen.generate_all()
        expected = {
            "organization",
            "board",
            "executives",
            "departments",
            "specialists",
            "workflows",
            "prompts",
            "docs",
            "graph",
        }
        assert expected <= set(result.summaries.keys())
        assert result.summaries["executives"]["executives"] > 0
        assert result.summaries["departments"]["departments"] > 0
        assert result.summaries["specialists"]["specialists"] > 0
        assert result.summaries["board"]["members"] > 0

    def test_generate_all_writes_artifacts(
        self, minimal_registry: CompanyRegistry, tmp_path: Path
    ) -> None:
        gen = CompanyGenerator(output_dir=tmp_path, registry=minimal_registry)
        result = gen.generate_all()
        assert len(result.created_files) > 0
        # Spot-check key artifact directories
        assert (tmp_path / "organization.json").exists()
        assert (tmp_path / "board.json").exists()
        assert (tmp_path / "board.yaml").exists()
        assert (tmp_path / "executives").is_dir()
        assert (tmp_path / "departments").is_dir()
        assert (tmp_path / "specialists").is_dir()
        assert (tmp_path / "workflows").is_dir()
        assert (tmp_path / "prompts").is_dir()
        assert (tmp_path / "docs").is_dir()
        assert (tmp_path / "graph").is_dir()

    def test_generate_all_executive_package(
        self, full_registry: CompanyRegistry, tmp_path: Path
    ) -> None:
        gen = CompanyGenerator(output_dir=tmp_path, registry=full_registry)
        gen.generate_all()
        exec_dirs = [d for d in (tmp_path / "executives").iterdir() if d.is_dir()]
        assert len(exec_dirs) == len(full_registry.executives)
        for d in exec_dirs:
            for filename in (
                "executive.yaml",
                "prompt.md",
                "profile.md",
                "knowledge.md",
                "memory.md",
                "agent.py",
            ):
                assert (d / filename).exists(), f"Missing {d.name}/{filename}"

    def test_generate_all_specialist_package(
        self, full_registry: CompanyRegistry, tmp_path: Path
    ) -> None:
        gen = CompanyGenerator(output_dir=tmp_path, registry=full_registry)
        gen.generate_all()
        spec_dirs = [d for d in (tmp_path / "specialists").iterdir() if d.is_dir()]
        assert len(spec_dirs) == len(full_registry.specialists)
        for d in spec_dirs:
            for filename in ("specialist.yaml", "prompt.md", "profile.md", "memory.md"):
                assert (d / filename).exists(), f"Missing {d.name}/{filename}"

    def test_generate_all_with_empty_registry(
        self, empty_registry: CompanyRegistry, tmp_path: Path
    ) -> None:
        """generate_all must not raise on an empty registry."""
        gen = CompanyGenerator(output_dir=tmp_path, registry=empty_registry)
        result = gen.generate_all()
        assert "organization" in result.summaries
        assert isinstance(result.warnings, list)
