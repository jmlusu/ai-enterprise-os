from pathlib import Path

from ai_company.company.graph_exporter import GraphExporter
from ai_company.graph.organization import OrganizationGraphEngine
from ai_company.registry.registry import RegistryEngine


class TestE2EGraph:
    def test_graph_engine_creates(self) -> None:
        g = OrganizationGraphEngine()
        assert g is not None

    def test_build_from_registry(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        assert result.registry is not None
        g = OrganizationGraphEngine()
        g.build_from_registry(result.registry)
        assert g.graph.number_of_nodes() > 0

    def test_graph_has_executive_nodes(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        g = OrganizationGraphEngine()
        g.build_from_registry(result.registry)
        exec_nodes = [
            n for n, d in g.graph.nodes(data=True) if d.get("type") == "executive"
        ]
        assert len(exec_nodes) > 0

    def test_graph_has_department_nodes(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        g = OrganizationGraphEngine()
        g.build_from_registry(result.registry)
        dept_nodes = [
            n for n, d in g.graph.nodes(data=True) if d.get("type") == "department"
        ]
        assert len(dept_nodes) > 0

    def test_graph_statistics(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        g = OrganizationGraphEngine()
        g.build_from_registry(result.registry)
        stats = g.get_statistics()
        assert stats["nodes"] > 0
        assert "density" in stats
        assert "is_dag" in stats

    def test_graph_to_json(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        g = OrganizationGraphEngine()
        g.build_from_registry(result.registry)
        js = g.to_json()
        assert '"nodes"' in js or "nodes" in js

    def test_graph_exporter_creates(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        exporter = GraphExporter(result.registry)
        result2 = exporter.generate()
        assert result2 is not None

    def test_graph_exporter_validate(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        exporter = GraphExporter(result.registry)
        errors = exporter.validate()
        assert len(errors) == 0

    def test_get_hierarchy_level(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        g = OrganizationGraphEngine()
        g.build_from_registry(result.registry)
        if g.graph.number_of_nodes() > 0:
            node = list(g.graph.nodes())[0]
            level = g.get_hierarchy_level(node)
            assert level >= 0

    def test_reporting_chain(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        g = OrganizationGraphEngine()
        g.build_from_registry(result.registry)
        if g.graph.number_of_nodes() > 0:
            node = list(g.graph.nodes())[0]
            chain = g.get_reporting_chain(node)
            assert len(chain) >= 1
