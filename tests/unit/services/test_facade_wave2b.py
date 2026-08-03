"""Unit tests for the wave 2b RuntimeFacade surface.

Covers the facade adapters added for Phase 2 Wave 2b / R5 / R6: the generate
runner, the decision approval inbox (incl. restart persistence), per-artifact
validators, the graph export write, company YAML CRUD, agent sync plumbing,
backup create/status, and telemetry persistence.

Every test is hermetic: the CWD is moved to ``tmp_path`` so the facade's
relative-path surfaces (``company/``, ``config/company/company.yaml``,
``runtime/decisions.jsonl``, ``backups/``) resolve to throwaway fixtures.
The runtime engine is created with a missing config dir (lenient defaults),
mirroring the golden parity fixture.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_company.models.company import (
    CompanyRegistry,
    DepartmentData,
    ExecutiveEntry,
    VisionData,
)
from ai_company.readmodel.engine import ReadModelEngine
from ai_company.runtime import create_runtime
from ai_company.services.runtime_facade import RuntimeFacade
from ai_company.telemetry.provider import record_provider_usage

_MISSING_CONFIG = "__missing__"

COMPANY_MANIFEST = """\
name: "Facade Test Co"
company_name: "Facade Test Holdings"
description: "Minimal manifest for facade wave 2b tests."
departments:
  - executive
  - engineering
"""

DEPARTMENTS_YAML = """\
executive:
  - CEO: "Runs the company"
engineering:
  - "Staff Engineer": "Builds things"
"""


@pytest.fixture()
def facade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RuntimeFacade:
    """A facade whose relative-path surfaces resolve inside ``tmp_path``."""
    monkeypatch.chdir(tmp_path)
    runtime = create_runtime(config_dir=_MISSING_CONFIG)
    return RuntimeFacade(config_dir=_MISSING_CONFIG, runtime=runtime)


@pytest.fixture()
def company_fixture(tmp_path: Path) -> None:
    """Write a minimal company manifest + departments YAML."""
    (tmp_path / "company").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "company").mkdir(parents=True, exist_ok=True)
    (tmp_path / "company" / "departments.yaml").write_text(
        DEPARTMENTS_YAML, encoding="utf-8"
    )
    (tmp_path / "config" / "company" / "company.yaml").write_text(
        COMPANY_MANIFEST, encoding="utf-8"
    )


class _FakeRunner:
    """In-memory stand-in for the GenerateRunner (start/cancel/log/list)."""

    def __init__(self) -> None:
        self._run: dict[str, Any] = {
            "run_id": "run-1",
            "target": "registry",
            "status": "running",
            "created_at": "2026-08-02T00:00:00+00:00",
            "started_at": "2026-08-02T00:00:01+00:00",
            "completed_at": None,
            "exit_code": None,
            "log_path": "runtime/generate_logs/run-1.log",
            "args": ["opencode", "run"],
        }

    def list_runs(self, limit: int = 50) -> list[Any]:
        return [_FakeRun(self._run)]

    def get(self, run_id: str) -> Any | None:
        return _FakeRun(self._run) if run_id == "run-1" else None

    def log_tail(self, run_id: str, max_lines: int = 400) -> list[str]:
        if run_id != "run-1":
            raise KeyError(f"run not found: {run_id}")
        return ["line one", "line two"]

    def start(self, target: str, reason: str = "") -> Any:
        if target == "bogus":
            raise ValueError(f"unknown generate target: {target}")
        return _FakeRun(self._run)

    def cancel(self, run_id: str) -> Any | None:
        if run_id != "run-1":
            return None
        return _FakeRun(self._run)


class _FakeRun:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


class TestGenerateFacade:
    def test_generate_runs_lists(self, facade: RuntimeFacade) -> None:
        facade._generate_runner = _FakeRunner()
        result = facade.generate_runs()
        assert result["success"] is True
        assert result["runs"][0]["run_id"] == "run-1"

    def test_generate_runs_carry_deep_link(self, facade: RuntimeFacade) -> None:
        facade._generate_runner = _FakeRunner()
        result = facade.generate_runs()
        assert result["runs"][0]["deep_link"].startswith(
            "opencode://new-session?directory="
        )

    def test_generate_run_carries_deep_link(self, facade: RuntimeFacade) -> None:
        facade._generate_runner = _FakeRunner()
        result = facade.generate_run("run-1")
        assert result["run"]["deep_link"].startswith("opencode://new-session?")

    def test_generate_targets_carry_deep_link(self, facade: RuntimeFacade) -> None:
        result = facade.generate_targets()
        assert result["success"] is True
        assert result["targets"]
        for target in result["targets"]:
            assert target["deep_link"].startswith("opencode://new-session?directory=")

    def test_generate_run_missing(self, facade: RuntimeFacade) -> None:
        facade._generate_runner = _FakeRunner()
        result = facade.generate_run("nope")
        assert result["success"] is False
        assert "not found" in result["errors"][0]

    def test_generate_log_tail(self, facade: RuntimeFacade) -> None:
        facade._generate_runner = _FakeRunner()
        result = facade.generate_log("run-1")
        assert result["lines"] == ["line one", "line two"]

    def test_generate_start_unknown_target(self, facade: RuntimeFacade) -> None:
        facade._generate_runner = _FakeRunner()
        result = facade.generate_start("bogus")
        assert result["success"] is False
        assert "unknown generate target" in result["errors"][0]

    def test_generate_cancel_missing(self, facade: RuntimeFacade) -> None:
        facade._generate_runner = _FakeRunner()
        result = facade.generate_cancel("nope")
        assert result["success"] is False


class TestDecisionInboxFacade:
    def test_create_and_list(self, facade: RuntimeFacade) -> None:
        result = facade.decision_create(
            title="Adopt SQLite read model",
            description="Rebuild the read path on SQLite (ADR 0004).",
            category="technical",
            priority="high",
            requester="dashboard",
            options=[
                {"id": "opt-a", "title": "SQLite"},
                {"id": "opt-b", "title": "Keep YAML"},
            ],
        )
        assert result["success"] is True
        decision = result["decision"]
        assert decision["title"] == "Adopt SQLite read model"
        assert decision["status"] in ("pending", "in_review")

        listed = facade.decisions_list()
        assert listed["success"] is True
        assert listed["count"] == 1
        assert listed["decisions"][0]["id"] == decision["id"]

    def test_get_includes_explanation(self, facade: RuntimeFacade) -> None:
        created = facade.decision_create(title="Pick a stack", description="...")[
            "decision"
        ]
        result = facade.decision_get(created["id"])
        assert result["success"] is True
        assert result["decision"]["id"] == created["id"]
        assert isinstance(result["explanation"], dict)

    def test_approve_resolves(self, facade: RuntimeFacade) -> None:
        created = facade.decision_create(
            title="Approve the plan",
            description="...",
            options=[{"id": "opt-a", "title": "Go"}, {"id": "opt-b", "title": "No"}],
        )["decision"]
        result = facade.decision_approve(
            created["id"], selected_option="opt-a", rationale="Board approved"
        )
        assert result["success"] is True
        assert result["decision"]["status"] == "approved"

    def test_approve_already_resolved(self, facade: RuntimeFacade) -> None:
        created = facade.decision_create(title="Once only", description="...")[
            "decision"
        ]
        facade.decision_approve(
            created["id"], selected_option="opt-a", rationale="done"
        )
        result = facade.decision_approve(
            created["id"], selected_option="opt-a", rationale="again"
        )
        assert result["success"] is False
        assert "already resolved" in result["errors"][0]

    def test_reject(self, facade: RuntimeFacade) -> None:
        created = facade.decision_create(title="Reject me", description="...")[
            "decision"
        ]
        result = facade.decision_reject(created["id"], reason="Not in scope")
        assert result["success"] is True
        assert result["decision"]["status"] == "rejected"

    def test_escalate_and_cancel(self, facade: RuntimeFacade) -> None:
        created = facade.decision_create(title="Escalate me", description="...")[
            "decision"
        ]
        escalated = facade.decision_escalate(created["id"], note="Needs CEO")
        assert escalated["success"] is True
        assert escalated["decision"]["status"] == "escalated"

        cancelled = facade.decision_cancel(created["id"], reason="Obsolete")
        assert cancelled["success"] is True
        assert cancelled["decision"]["status"] == "cancelled"

    def test_missing_decision(self, facade: RuntimeFacade) -> None:
        assert facade.decision_get("nope")["success"] is False
        assert facade.decision_approve("nope", "opt-a", "x")["success"] is False
        assert facade.decision_reject("nope", "x")["success"] is False

    def test_inbox_survives_restart(self, facade: RuntimeFacade) -> None:
        created = facade.decision_create(title="Persist me", description="...")[
            "decision"
        ]
        # A brand-new facade (fresh DecisionEngine) must rebuild the inbox
        # from the JSONL history via import_decisions().
        restarted = RuntimeFacade(config_dir=_MISSING_CONFIG)
        result = restarted.decision_get(created["id"])
        assert result["success"] is True
        assert result["decision"]["title"] == "Persist me"


class TestValidatorsFacade:
    @pytest.mark.parametrize(
        "artifact", ["yaml", "registry", "templates", "manifest", "output"]
    )
    def test_each_artifact_runs(
        self, facade: RuntimeFacade, company_fixture: None, artifact: str
    ) -> None:
        # The minimal fixture does not satisfy every pass (e.g. templates/
        # and generated/ are absent), so we assert the response *shape*:
        # exactly one report, no facade-level errors, and a summary line.
        result = facade.validate_artifacts(artifact=artifact)
        assert result["artifact"] == artifact
        assert result["errors"] == []
        assert len(result["reports"]) == 1
        assert isinstance(result["success"], bool)
        assert "summary" in result

    def test_unknown_artifact(self, facade: RuntimeFacade) -> None:
        result = facade.validate_artifacts(artifact="bogus")
        assert result["success"] is False
        assert "unknown artifact" in result["errors"][0]

    def test_all_artifact_count(
        self, facade: RuntimeFacade, company_fixture: None
    ) -> None:
        result = facade.validate_artifacts(artifact="all")
        assert result["errors"] == []
        # validate_all() runs the five per-artifact passes.
        assert len(result["reports"]) == 5


class TestGraphExportWrite:
    def test_export_writes_artifacts(
        self,
        tmp_path: Path,
        facade: RuntimeFacade,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        registry = CompanyRegistry(
            vision=VisionData(name="TestCo", company_name="TestCo Inc"),
            executives=[
                ExecutiveEntry(name="CEO Alice", title="CEO", department="executive"),
            ],
            departments={
                "executive": DepartmentData(name="executive"),
            },
        )

        class _LoadResult:
            pass

        _LoadResult.registry = registry  # class bodies cannot close over locals

        monkeypatch.setattr(
            "ai_company.registry.registry.RegistryEngine.load",
            lambda *args, **kwargs: _LoadResult(),
        )

        result = facade.graph_export_write(output_dir="generated")
        assert result["success"] is True
        assert any(path.endswith("org_chart.mmd") for path in result["files"])
        assert any(path.endswith("graph_enriched.json") for path in result["files"])
        assert (tmp_path / "generated" / "graph" / "org_chart.mmd").is_file()
        assert (tmp_path / "generated" / "graph" / "graph_enriched.json").is_file()


class TestCompanyCrudFacade:
    def test_company_files(self, facade: RuntimeFacade, company_fixture: None) -> None:
        result = facade.company_files()
        assert result["success"] is True
        assert "departments.yaml" in result["files"]

    def test_department_add_and_manifest(
        self, facade: RuntimeFacade, company_fixture: None
    ) -> None:
        result = facade.company_department_add("Data Science", title="Data Lead")
        assert result["success"] is True
        assert result["department"] == "data-science"

        departments = (Path("company") / "departments.yaml").read_text(encoding="utf-8")
        assert "data-science" in departments
        manifest = (Path("config/company") / "company.yaml").read_text(encoding="utf-8")
        assert "data-science" in manifest

    def test_department_add_duplicate(
        self, facade: RuntimeFacade, company_fixture: None
    ) -> None:
        facade.company_department_add("Data Science")
        result = facade.company_department_add("Data Science")
        assert result["success"] is False
        assert "exists" in result["errors"][0]

    def test_department_add_invalid_name(
        self, facade: RuntimeFacade, company_fixture: None
    ) -> None:
        result = facade.company_department_add("!!!")
        assert result["success"] is False

    def test_department_remove(
        self, facade: RuntimeFacade, company_fixture: None
    ) -> None:
        facade.company_department_add("Data Science")
        result = facade.company_department_remove("Data Science")
        assert result["success"] is True
        assert result["department"] == "data-science"

        departments = (Path("company") / "departments.yaml").read_text(encoding="utf-8")
        assert "data-science" not in departments
        manifest = (Path("config/company") / "company.yaml").read_text(encoding="utf-8")
        assert "data-science" not in manifest

    def test_department_remove_missing(
        self, facade: RuntimeFacade, company_fixture: None
    ) -> None:
        result = facade.company_department_remove("never-existed")
        assert result["success"] is False
        assert "not found" in result["errors"][0]

    def test_manifest_update(
        self, facade: RuntimeFacade, company_fixture: None
    ) -> None:
        result = facade.company_manifest_update(
            name="Renamed Co", company_name="Renamed Holdings"
        )
        assert result["success"] is True
        assert set(result["changed"]) == {"name", "company_name"}
        manifest = (Path("config/company") / "company.yaml").read_text(encoding="utf-8")
        assert "Renamed Co" in manifest


class TestAgentsSyncFacade:
    def test_invalid_scope(self, facade: RuntimeFacade) -> None:
        result = facade.agents_sync(scope="bogus")
        assert result["success"] is False
        assert "invalid scope" in result["errors"][0]

    def test_sync_run_reports_counts(
        self, facade: RuntimeFacade, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Result:
            errors: list[str] = []
            created: list[str] = [".opencode/agent/ceo.md"]
            updated: list[str] = []
            skipped: list[str] = []
            conflicts: list[str] = []

        class _Engine:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs

            def run(self) -> _Result:
                assert self.kwargs["config"].scope == "project"
                assert self.kwargs["config"].force is False
                return _Result()

        monkeypatch.setattr("ai_company.agents.sync.AgentSyncEngine", _Engine)
        result = facade.agents_sync(scope="project", force=False)
        assert result["success"] is True
        assert result["created"] == [".opencode/agent/ceo.md"]


class TestBackupFacade:
    def test_create_and_status(self, facade: RuntimeFacade, tmp_path: Path) -> None:
        (tmp_path / "company").mkdir(parents=True, exist_ok=True)
        (tmp_path / "company" / "company.yaml").write_text(
            "name: x\n", encoding="utf-8"
        )
        (tmp_path / "runtime").mkdir(parents=True, exist_ok=True)
        (tmp_path / "runtime" / "events.jsonl").write_text("{}\n", encoding="utf-8")

        created = facade.backup_create(dest_dir="backups")
        assert created["success"] is True
        assert str(created["path"]).endswith(".tar.gz")

        status = facade.backup_status()
        assert status["success"] is True
        assert status["total"] == 1
        assert status["backups"][0]["name"].endswith(".tar.gz")
        assert status["backups"][0]["size_bytes"] > 0

    def test_status_empty(self, facade: RuntimeFacade) -> None:
        status = facade.backup_status()
        assert status["success"] is True
        assert status["total"] == 0
        assert status["backups"] == []


class TestTelemetryFacade:
    def test_metrics_persist_and_summary(
        self,
        facade: RuntimeFacade,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target = tmp_path / "runtime" / "metrics_history.jsonl"
        monkeypatch.setattr(
            "ai_company.telemetry.metrics.METRICS_HISTORY_RELATIVE_PATH",
            target.relative_to(tmp_path),
        )

        result = facade.metrics_persist()
        assert result["success"] is True
        assert isinstance(result["snapshot"], dict)
        # T4 — recovery-outcome fields flow through the persisted snapshot
        # (defaults of zero with no recovery activity in this fixture).
        snapshot = result["snapshot"]
        assert snapshot["recovery_attempts"] == 0
        assert snapshot["recovery_successes"] == 0
        assert snapshot["recovery_failures"] == 0
        assert snapshot["recovery_success_rate"] == 0.0

        summary = facade.metrics_history_summary()
        assert summary["success"] is True
        assert summary["summary"]["samples"] >= 1
        trend = summary["summary"]["trend"]
        assert "recovery_attempts" in trend
        assert "recovery_success_rate" in trend

    def test_provider_usage_summary(
        self,
        facade: RuntimeFacade,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target = tmp_path / "runtime" / "provider_usage.jsonl"
        monkeypatch.setattr(
            "ai_company.telemetry.provider.PROVIDER_USAGE_RELATIVE_PATH",
            target.relative_to(tmp_path),
        )

        record_provider_usage(
            provider="opencode",
            model="north-mini-code-free",
            usage={"prompt_tokens": 100, "completion_tokens": 50},
            latency_seconds=1.5,
            ok=True,
        )

        summary = facade.provider_usage_summary()
        assert summary["success"] is True
        rows = {row["model"]: row for row in summary["summary"]["models"]}
        assert "north-mini-code-free" in rows
        assert rows["north-mini-code-free"]["requests"] == 1
        assert rows["north-mini-code-free"]["total_tokens"] == 150

    def test_alerts_summary(
        self,
        facade: RuntimeFacade,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target = tmp_path / "runtime" / "alerts.jsonl"
        monkeypatch.setattr(
            "ai_company.telemetry.alerts.ALERTS_RELATIVE_PATH",
            target.relative_to(tmp_path),
        )
        from ai_company.telemetry.alerts import (
            record_alert_open,
            record_alert_resolved,
        )

        record_alert_open(component="engine-a", reason="heartbeat_timeout", attempts=2)
        record_alert_resolved(component="engine-a", reason="unisolated")

        summary = facade.alerts_summary()
        assert summary["success"] is True
        assert summary["summary"]["records"] == 2
        assert summary["summary"]["open_count"] == 0
        assert summary["summary"]["open_alerts"] == []

    def test_retention_status(
        self,
        facade: RuntimeFacade,
        tmp_path: Path,
    ) -> None:
        """T2 — dry-run report reads raw counts per source, never mutates."""
        (tmp_path / "runtime").mkdir(parents=True, exist_ok=True)
        (tmp_path / "runtime" / "metrics_history.jsonl").write_text(
            json.dumps(
                {
                    "timestamp": "2026-08-01T10:00:00+00:00",
                    "snapshot": {"cpu_percent": 12.0},
                }
            )
            + "\n"
            + json.dumps(
                {
                    "timestamp": "2026-08-02T10:00:00+00:00",
                    "snapshot": {"cpu_percent": 10.0},
                }
            )
            + "\n",
            encoding="utf-8",
        )

        summary = facade.retention_status()
        assert summary["success"] is True
        report = summary["summary"]
        assert report["applied"] is False  # read-only dry run
        metrics = next(s for s in report["sources"] if s["key"] == "metrics_history")
        assert metrics["raw_records"] == 2
        assert metrics["days"] == 7
        assert metrics["rollup"] is True

    def test_session_telemetry_record_and_summary(
        self,
        facade: RuntimeFacade,
        tmp_path: Path,
    ) -> None:
        """P2 — checkpoint record persists; summary dedups to newest per session."""
        record = {
            "session_id": "sess-1",
            "title": "Sprint 5.5 P2",
            "messages_user": 2,
            "messages_assistant": 3,
            "tool_calls": 4,
            "commands_run": 1,
            "tools_used": {"read": 2},
            "end_reason": "idle",
        }
        result = facade.session_telemetry_record(dict(record))
        assert result["success"] is True
        assert result["session_id"] == "sess-1"

        record["end_reason"] = "deleted"
        record["messages_assistant"] = 4
        result = facade.session_telemetry_record(dict(record))
        assert result["success"] is True

        summary = facade.session_telemetry_summary()
        assert summary["success"] is True
        data = summary["summary"]
        assert data["sessions"] == 1
        assert data["records"] == 2
        assert data["recent"][0]["messages_assistant"] == 4
        assert data["recent"][0]["end_reason"] == "deleted"
        assert data["totals"]["tool_calls"] == 4


def _write_metrics_and_usage(tmp_path: Path) -> dict[str, Path]:
    """Write tiny telemetry JSONL fixtures under ``tmp_path`` (T1)."""
    metrics_path = tmp_path / "runtime" / "metrics_history.jsonl"
    usage_path = tmp_path / "runtime" / "provider_usage.jsonl"
    events_path = tmp_path / "events" / "store.jsonl"
    for path in (metrics_path, usage_path, events_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(
        "\n".join(
            json.dumps(
                {
                    "timestamp": f"2026-08-01T10:0{i}:00+00:00",
                    "snapshot": {
                        "uptime_seconds": 10.0 + i,
                        "gauges": {
                            "cpu_percent": 10.0 + i,
                            "memory_percent": 40.0,
                            "engine_healthy": 6,
                            "engine_degraded": 0,
                            "engine_failed": 0,
                        },
                        "counters": {"jobs_executed": i, "jobs_failed": 0},
                    },
                },
                ensure_ascii=False,
            )
            for i in range(2)
        )
        + "\n",
        encoding="utf-8",
    )
    usage_path.write_text(
        "\n".join(
            json.dumps(
                {
                    "timestamp": "2026-08-01T10:00:00+00:00",
                    "provider": "OllamaProvider",
                    "model": "llama3",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    "latency_seconds": 0.5,
                    "ok": True,
                    "error": "",
                },
                ensure_ascii=False,
            )
            for _ in range(2)
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "events_path": events_path,
        "metrics_path": metrics_path,
        "provider_usage_path": usage_path,
    }


class TestTelemetryReadModelFacade:
    """T1 — facade telemetry reads prefer the SQLite read model store."""

    @pytest.fixture()
    def read_model(self, facade: RuntimeFacade, tmp_path: Path) -> ReadModelEngine:
        """Register a real ReadModelEngine on the facade's runtime."""
        sources = _write_metrics_and_usage(tmp_path)
        engine = ReadModelEngine(
            db_path=tmp_path / "runtime" / "dashboard.db", **sources
        )
        facade.runtime.register_engine("read_model", engine)
        return engine

    def test_metrics_read_served_from_store(
        self, facade: RuntimeFacade, read_model: ReadModelEngine
    ) -> None:
        summary = facade.metrics_history_summary()
        assert summary["success"] is True
        assert summary["summary"]["samples"] == 2
        # Store-backed reads keep the same envelope the JSONL path produced.
        assert summary["summary"]["persistence_enabled"] is True

    def test_provider_usage_read_served_from_store(
        self, facade: RuntimeFacade, read_model: ReadModelEngine
    ) -> None:
        usage = facade.provider_usage_summary()
        assert usage["success"] is True
        assert usage["summary"]["records"] == 2
        by_model = {row["model"]: row for row in usage["summary"]["models"]}
        assert by_model["llama3"]["requests"] == 2

    def test_sync_read_model_catches_up_without_restart(
        self, facade: RuntimeFacade, tmp_path: Path, read_model: ReadModelEngine
    ) -> None:
        # Append a third metric line to the JSONL source after the rebuild.
        metrics_path = tmp_path / "runtime" / "metrics_history.jsonl"
        with metrics_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "timestamp": "2026-08-01T11:00:00+00:00",
                        "snapshot": {
                            "uptime_seconds": 30.0,
                            "gauges": {
                                "cpu_percent": 3.0,
                                "memory_percent": 41.0,
                                "engine_healthy": 6,
                                "engine_degraded": 0,
                                "engine_failed": 0,
                            },
                            "counters": {"jobs_executed": 8, "jobs_failed": 0},
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

        # The store is stale (reads served from the projection, not JSONL)…
        assert facade.metrics_history_summary()["summary"]["samples"] == 2
        # …until the periodic sync — no restart needed.
        result = facade.sync_read_model()
        assert result["synced"] is True
        assert facade.metrics_history_summary()["summary"]["samples"] == 3

    def test_metrics_persist_syncs_read_model(
        self, facade: RuntimeFacade, read_model: ReadModelEngine
    ) -> None:
        result = facade.metrics_persist()
        assert result["success"] is True
        # The persisted snapshot was synced into the projection.
        assert read_model.stats()["metrics_history"] >= 1

    def test_reads_fall_back_to_jsonl_without_store(
        self, facade: RuntimeFacade, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No read_model engine registered → JSONL path (pre-existing behavior).
        target = tmp_path / "runtime" / "metrics_history.jsonl"
        monkeypatch.setattr(
            "ai_company.telemetry.metrics.METRICS_HISTORY_RELATIVE_PATH",
            target.relative_to(tmp_path),
        )
        facade.metrics_persist()
        summary = facade.metrics_history_summary()
        assert summary["success"] is True
        assert summary["summary"]["samples"] >= 1
        assert summary["summary"]["persistence_enabled"] is True
