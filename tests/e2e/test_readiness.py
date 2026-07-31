"""Readiness validation - checks that all platform components are operational."""

from pathlib import Path

from ai_company.audit.engine import AuditEngine
from ai_company.decision.engine import DecisionEngine
from ai_company.memory.engine import MemoryEngine


class TestE2EReadiness:
    def test_audit_engine_creates(self) -> None:
        engine = AuditEngine()
        assert engine is not None

    def test_audit_record_event(self) -> None:
        engine = AuditEngine()
        event = engine.record("test_event", engine="test", action="test_action")
        assert event.event_type == "test_event"

    def test_audit_session(self) -> None:
        engine = AuditEngine()
        session_id = engine.start_session("test_session")
        assert session_id is not None
        assert engine.end_session(session_id)

    def test_audit_query(self) -> None:
        engine = AuditEngine()
        engine.record("query_test", engine="test", action="query")
        results = engine.query(limit=10)
        assert len(results) >= 1

    def test_audit_metrics(self) -> None:
        engine = AuditEngine()
        metrics = engine.get_metrics()
        assert metrics is not None

    def test_audit_get_events(self) -> None:
        engine = AuditEngine()
        engine.record("event_test", engine="test", action="events")
        events = engine.get_events(limit=10)
        assert len(events) >= 1

    def test_memory_and_decision_integration(self) -> None:
        mem = MemoryEngine()
        dec = DecisionEngine()
        d = dec.create_decision(
            title="Integration Test",
            description="Testing memory-decision integration",
        )
        entry = mem.save(
            {"decision_id": d.id, "title": d.title},
            memory_type="decision",
            tags=["integration"],
        )
        retrieved = mem.retrieve(entry.id)
        assert retrieved is not None
        assert retrieved.content["decision_id"] == d.id

    def test_all_engines_instantiate(self) -> None:
        assert DecisionEngine() is not None
        assert MemoryEngine() is not None
        assert AuditEngine() is not None

    def test_templates_exist(self) -> None:
        tmpl_dir = Path("templates")
        assert tmpl_dir.is_dir()
        templates = list(tmpl_dir.glob("*.j2"))
        assert len(templates) >= 2

    def test_config_files_exist(self) -> None:
        config_dir = Path("config")
        assert config_dir.is_dir()
        assert (config_dir / "company" / "company.yaml").exists()

    def test_company_yaml_exists(self) -> None:
        assert Path("company/company.yaml").exists()

    def test_docs_exist(self) -> None:
        docs = Path("docs")
        assert docs.is_dir()
        md_files = list(docs.glob("*.md"))
        assert len(md_files) >= 1

    def test_pyproject_toml(self) -> None:
        assert Path("pyproject.toml").exists()
