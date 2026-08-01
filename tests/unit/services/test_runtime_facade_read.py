"""Unit tests for the Phase 1 read-only RuntimeFacade surface (WS-1.0).

Every test is hermetic: registry/graph/report/validate methods point at a
minimal on-disk fixture (``tmp_path``), memory methods inject an explicit
:class:`MemoryEngine`, and orchestration methods inject an engine stub so
nothing touches the real ``company/`` tree or writes to ``memory/``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_company.memory.engine import MemoryEngine
from ai_company.services.runtime_facade import RuntimeFacade

COMPANY_YAML = """\
name: "Facade Test Co"
description: "Minimal fixture for facade tests."
company_name: "Facade Test Holdings"
departments:
  - executive
  - engineering
"""

DEPARTMENTS_YAML = """\
executive:
  - CEO: "Runs the company"
  - COO: "Runs operations"
engineering:
  - "Staff Engineer": "Builds things"
"""

EXECUTIVES_YAML = """\
members:
  - name: "Ada Lovelace"
    title: "Chief Executive Officer"
    department: "executive"
    responsibilities:
      - "Set direction"
    kpis:
      - "Revenue"
    budget_authority: 1000000
    reports_to: "Board of Directors"
    start_date: "2023-01-01"
    email: "ada@test.example"
    agent_config:
      model: "gpt-4o"
      instructions: "Run the company."
      tools:
        - "registry-read"
      temperature: 0.2
  - name: "Grace Hopper"
    title: "Chief Technology Officer"
    department: "engineering"
    responsibilities:
      - "Architecture"
    kpis:
      - "Uptime"
    budget_authority: 500000
    reports_to: "Ada Lovelace"
    start_date: "2023-02-01"
    email: "grace@test.example"
    agent_config:
      model: "gpt-4o"
      instructions: "Own tech."
      tools:
        - "registry-read"
      temperature: 0.1
"""

BOARD_YAML = """\
members:
  - name: "Board Member One"
    role: "Chair"
"""

WORKFLOWS_YAML = """\
items:
  - name: "onboard"
    description: "Onboard a new hire."
    steps:
      - "Create account"
"""

SPECIALISTS_YAML = """\
list:
  - name: "Legal Advisor"
    expertise: "Provides legal guidance."
"""

POLICIES_YAML = """\
items:
  - name: "Expense Policy"
    description: "Rules for expenses."
"""

CONFIG_COMPANY_YAML = """\
vision:
  name: "Facade Test Vision"
  description: "Test vision."
company_name: "Facade Test Holdings"
"""


@pytest.fixture
def company_dir(tmp_path: Path) -> Path:
    """A minimal, valid on-disk company fixture."""
    d = tmp_path / "company"
    d.mkdir()
    (d / "company.yaml").write_text(COMPANY_YAML, encoding="utf-8")
    (d / "departments.yaml").write_text(DEPARTMENTS_YAML, encoding="utf-8")
    (d / "executives.yaml").write_text(EXECUTIVES_YAML, encoding="utf-8")
    (d / "board.yaml").write_text(BOARD_YAML, encoding="utf-8")
    (d / "workflows.yaml").write_text(WORKFLOWS_YAML, encoding="utf-8")
    (d / "specialists.yaml").write_text(SPECIALISTS_YAML, encoding="utf-8")
    (d / "policies.yaml").write_text(POLICIES_YAML, encoding="utf-8")
    return d


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    d = tmp_path / "config-company"
    d.mkdir()
    (d / "company.yaml").write_text(CONFIG_COMPANY_YAML, encoding="utf-8")
    return d


@pytest.fixture
def memory_engine(tmp_path: Path) -> MemoryEngine:
    """A real MemoryEngine pointed at a temp store (no repo writes)."""
    from ai_company.memory.engine import MemoryEntry
    from ai_company.memory.models import MemoryNamespace, MemoryType

    engine = MemoryEngine(storage_path=str(tmp_path / "mem.jsonl"))
    engine.store.save(
        MemoryEntry(
            id="mem-1",
            memory_type=MemoryType.DECISION,
            namespace=MemoryNamespace.EXECUTIVE,
            content={"note": "Approved the facade expansion."},
            importance=0.8,
            tags=["phase1"],
        )
    )
    engine.store.save(
        MemoryEntry(
            id="mem-2",
            memory_type=MemoryType.DECISION,
            namespace=MemoryNamespace.EXECUTIVE,
            content={"note": "Rejected SQLite for v1."},
            importance=0.7,
            tags=["phase1"],
        )
    )
    return engine


class TestRegistryMethods:
    def test_registry_list_ok(self, company_dir: Path, config_dir: Path) -> None:
        facade = RuntimeFacade()
        result = facade.registry_list(company_dir=company_dir, config_dir=config_dir)
        assert result["success"] is True
        assert result["errors"] == []
        reg = result["registry"]
        assert reg["vision"]["name"] == "Facade Test Co"
        assert reg["departments"]["executive"]["roles"] == 2
        assert reg["executives"] == 2
        assert reg["board"] == 1
        assert reg["workflows"] == 1

    def test_registry_list_missing_dir(self, tmp_path: Path) -> None:
        # Parity with the CLI: a missing company dir loads an empty registry
        # (no hard error) — the vision name is blank, so the UI renders it
        # as "data pending" rather than faking values.
        facade = RuntimeFacade()
        result = facade.registry_list(company_dir=tmp_path / "nope")
        assert result["success"] is True
        assert result["registry"]["vision"]["name"] == ""

    def test_registry_show_vision(self, company_dir: Path, config_dir: Path) -> None:
        facade = RuntimeFacade()
        result = facade.registry_show(
            "vision", company_dir=company_dir, config_dir=config_dir
        )
        assert result["success"] is True
        assert result["entry"]["name"] == "Facade Test Co"

    def test_registry_show_departments(
        self, company_dir: Path, config_dir: Path
    ) -> None:
        facade = RuntimeFacade()
        result = facade.registry_show(
            "departments", company_dir=company_dir, config_dir=config_dir
        )
        assert result["success"] is True
        assert "executive" in result["entry"]
        assert result["entry"]["engineering"]["roles"][0]["title"] == "Staff Engineer"

    def test_registry_show_single_department(
        self, company_dir: Path, config_dir: Path
    ) -> None:
        facade = RuntimeFacade()
        result = facade.registry_show(
            "engineering", company_dir=company_dir, config_dir=config_dir
        )
        assert result["success"] is True
        assert result["entry"]["name"] == "engineering"

    def test_registry_show_unknown(self, company_dir: Path, config_dir: Path) -> None:
        facade = RuntimeFacade()
        result = facade.registry_show(
            "bogus", company_dir=company_dir, config_dir=config_dir
        )
        assert result["success"] is False
        assert "Unknown entry" in result["errors"][0]

    def test_registry_verify(self, company_dir: Path, config_dir: Path) -> None:
        facade = RuntimeFacade()
        result = facade.registry_verify(company_dir=company_dir, config_dir=config_dir)
        assert result["success"] is True
        assert result["valid"] is True
        assert result["departments"] == 2


class TestExecutivesMethods:
    def test_executives_list(self, company_dir: Path, config_dir: Path) -> None:
        facade = RuntimeFacade()
        result = facade.executives_list(company_dir=company_dir, config_dir=config_dir)
        assert result["success"] is True
        names = {ex["name"] for ex in result["executives"]}
        assert names == {"Ada Lovelace", "Grace Hopper"}
        ada = next(ex for ex in result["executives"] if ex["name"] == "Ada Lovelace")
        assert ada["title"] == "Chief Executive Officer"
        assert ada["department"] == "executive"

    def test_executive_show_case_insensitive(
        self, company_dir: Path, config_dir: Path
    ) -> None:
        facade = RuntimeFacade()
        result = facade.executive_show(
            "ada lovelace", company_dir=company_dir, config_dir=config_dir
        )
        assert result["success"] is True
        ex = result["executive"]
        assert ex["name"] == "Ada Lovelace"
        assert ex["budget_authority"] == 1000000
        assert ex["agent_config"]["model"] == "gpt-4o"
        assert ex["reports_to"] == "Board of Directors"

    def test_executive_show_not_found(
        self, company_dir: Path, config_dir: Path
    ) -> None:
        facade = RuntimeFacade()
        result = facade.executive_show(
            "Nobody", company_dir=company_dir, config_dir=config_dir
        )
        assert result["success"] is False
        assert "not found" in result["errors"][0]

    def test_org_chart(self, company_dir: Path, config_dir: Path) -> None:
        facade = RuntimeFacade()
        result = facade.org_chart(company_dir=company_dir, config_dir=config_dir)
        assert result["success"] is True
        assert result["executives"] == 2
        assert "mermaid" in result
        assert "graph TD" in result["mermaid"]
        assert "Ada_Lovelace" in result["mermaid"]


class TestMemoryMethods:
    def test_memory_list_all(self, memory_engine: MemoryEngine) -> None:
        facade = RuntimeFacade()
        result = facade.memory_list(memory_engine=memory_engine)
        assert result["success"] is True
        assert result["count"] == 2

    def test_memory_list_by_type(self, memory_engine: MemoryEngine) -> None:
        facade = RuntimeFacade()
        result = facade.memory_list(memory_type="decision", memory_engine=memory_engine)
        assert result["count"] == 2

    def test_memory_list_by_namespace(self, memory_engine: MemoryEngine) -> None:
        facade = RuntimeFacade()
        result = facade.memory_list(namespace="executive", memory_engine=memory_engine)
        assert result["success"] is True
        assert result["count"] == 2

    def test_memory_get(self, memory_engine: MemoryEngine) -> None:
        facade = RuntimeFacade()
        result = facade.memory_get("mem-1", memory_engine=memory_engine)
        assert result["success"] is True
        assert result["entry"]["content"]["note"].startswith("Approved")

    def test_memory_get_missing(self, memory_engine: MemoryEngine) -> None:
        facade = RuntimeFacade()
        result = facade.memory_get("nope", memory_engine=memory_engine)
        assert result["success"] is False
        assert "not found" in result["errors"][0]

    def test_memory_search(self, memory_engine: MemoryEngine) -> None:
        facade = RuntimeFacade()
        result = facade.memory_search(query="SQLite", memory_engine=memory_engine)
        assert result["success"] is True
        assert result["count"] >= 1

    def test_memory_stats(self, memory_engine: MemoryEngine) -> None:
        facade = RuntimeFacade()
        result = facade.memory_stats(memory_engine=memory_engine)
        assert result["success"] is True
        assert result["stats"]["total_memories"] == 2

    def test_memory_snapshots(self, memory_engine: MemoryEngine) -> None:
        facade = RuntimeFacade()
        result = facade.memory_snapshots(memory_engine=memory_engine)
        assert result["success"] is True
        assert isinstance(result["snapshots"], list)

    def test_memory_list_bad_engine(self) -> None:
        facade = RuntimeFacade()

        class Broken:
            def retrieve_all(self) -> Any:  # pragma: no cover
                raise RuntimeError("boom")

        result = facade.memory_list(memory_engine=Broken())
        assert result["success"] is False
        assert result["errors"] == ["boom"]


class TestGraphMethods:
    def test_graph_show(self, company_dir: Path, config_dir: Path) -> None:
        facade = RuntimeFacade()
        result = facade.graph_show(company_dir=company_dir, config_dir=config_dir)
        assert result["success"] is True
        assert result["vision"] == "Facade Test Co"
        assert result["executives"] == 2
        assert result["edges"] == 3  # 3 department roles

    def test_graph_stats(self, company_dir: Path, config_dir: Path) -> None:
        facade = RuntimeFacade()
        result = facade.graph_stats(company_dir=company_dir, config_dir=config_dir)
        assert result["success"] is True
        assert result["nodes"] == 1 + 2 + 3  # root + departments + roles
        assert result["edges"] == 3
        assert 0 <= result["density"] <= 1


class TestReportsMethods:
    def test_reports_list(self) -> None:
        facade = RuntimeFacade()
        result = facade.reports_list()
        assert result["types"] == ["summary", "detailed", "health"]

    def test_report_summary(self, company_dir: Path, config_dir: Path) -> None:
        facade = RuntimeFacade()
        result = facade.report_generate_read(
            "summary", company_dir=company_dir, config_dir=config_dir
        )
        assert result["success"] is True
        assert result["company"] == "Facade Test Holdings"
        assert result["departments"] == 2
        assert result["roles"] == 3

    def test_report_detailed(self, company_dir: Path, config_dir: Path) -> None:
        facade = RuntimeFacade()
        result = facade.report_generate_read(
            "detailed", company_dir=company_dir, config_dir=config_dir
        )
        assert result["success"] is True
        assert len(result["executives"]) == 2

    def test_report_health(self, company_dir: Path, config_dir: Path) -> None:
        facade = RuntimeFacade()
        result = facade.report_generate_read(
            "health", company_dir=company_dir, config_dir=config_dir
        )
        assert result["success"] is True
        assert "validation" in result

    def test_report_unknown_type(self) -> None:
        facade = RuntimeFacade()
        result = facade.report_generate_read("bogus")
        assert result["success"] is False
        assert "Unknown report type" in result["errors"][0]


class TestValidateMethods:
    def test_validate_read(self, company_dir: Path, config_dir: Path) -> None:
        facade = RuntimeFacade()
        result = facade.validate_read(company_dir=company_dir, config_dir=config_dir)
        assert result["success"] is True
        assert "passed" in result
        assert isinstance(result["reports"], list)


class TestOrchestrationMethods:
    class StubEngine:
        def engine_status(self) -> Any:
            class Status:
                def model_dump(self, mode: str = "json") -> dict[str, Any]:
                    return {"phase": "idle", "mode": mode}

            return Status()

        def history(self, plan_id: str | None = None) -> list[Any]:
            class Record:
                def model_dump(self, mode: str = "json") -> dict[str, Any]:
                    return {"plan_id": plan_id, "mode": mode, "id": "r1"}

            return [Record()]

        def close(self) -> None:
            return None

    def test_orchestration_status_injected(self) -> None:
        facade = RuntimeFacade()
        result = facade.orchestration_status(engine=self.StubEngine())
        assert result["success"] is True
        assert result["engine"]["phase"] == "idle"

    def test_orchestration_history_injected(self) -> None:
        facade = RuntimeFacade()
        result = facade.orchestration_history(
            plan_id="plan-1", engine=self.StubEngine()
        )
        assert result["success"] is True
        assert result["count"] == 1
        assert result["records"][0]["plan_id"] == "plan-1"


class TestGenerateTargets:
    def test_generate_targets_has_expected_keys(self) -> None:
        facade = RuntimeFacade()
        result = facade.generate_targets()
        assert result["success"] is True
        assert len(result["targets"]) > 0
        keys = {t["key"] for t in result["targets"]}
        assert "registry" in keys
        assert "dashboard" in keys
        for target in result["targets"]:
            assert "description" in target
            assert "prompt_file" in target


class TestCoreSurface:
    def test_phase_and_status(self) -> None:
        facade = RuntimeFacade()
        assert facade.phase in ("stopped", "running", "failed", "unknown")
        assert isinstance(facade.status(), dict)

    def test_health_summary_returns_dict(self) -> None:
        facade = RuntimeFacade()
        summary = facade.health_summary()
        assert isinstance(summary, dict)
