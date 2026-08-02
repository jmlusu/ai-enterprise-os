"""Tests for the SQLite (WAL) derived read model (ADR 0004).

Covers the store (schema, rebuild from JSONL sources, reads) and the
runtime engine (construction-time rebuild = the "on startup" trigger,
health probe, restart, read passthroughs).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_company.readmodel.engine import ReadModelEngine
from ai_company.readmodel.store import ReadModelStore

EVENT_LINES = [
    {
        "_type": "event",
        "metadata": {
            "event_id": "evt_1",
            "timestamp": "2026-08-01T10:00:00+00:00",
            "event_type": "workflow.started",
            "source": "orchestration",
            "status": "delivered",
        },
        "payload": {"pipeline": "default"},
    },
    {
        "_type": "event",
        "metadata": {
            "event_id": "evt_2",
            "timestamp": "2026-08-01T10:05:00+00:00",
            "event_type": "workflow.completed",
            "source": "orchestration",
            "status": "delivered",
        },
        "payload": {"pipeline": "default"},
    },
    {
        "_type": "event",
        "metadata": {
            "event_id": "evt_3",
            "timestamp": "2026-08-01T10:06:00+00:00",
            "event_type": "decision.approved",
            "source": "decision",
            "status": "delivered",
        },
        "payload": {"decision_id": "d1"},
    },
]

METRIC_LINES = [
    {
        "timestamp": "2026-08-01T10:00:00+00:00",
        "snapshot": {
            "uptime_seconds": 12.5,
            "gauges": {
                "cpu_percent": 12.3,
                "memory_percent": 40.1,
                "engine_healthy": 6,
                "engine_degraded": 0,
                "engine_failed": 0,
            },
            "counters": {"jobs_executed": 3, "jobs_failed": 0},
        },
    },
    {
        "timestamp": "2026-08-01T10:05:00+00:00",
        "snapshot": {
            "uptime_seconds": 17.5,
            "gauges": {
                "cpu_percent": 9.8,
                "memory_percent": 41.0,
                "engine_healthy": 6,
                "engine_degraded": 0,
                "engine_failed": 0,
            },
            "counters": {"jobs_executed": 5, "jobs_failed": 1},
        },
    },
]

USAGE_LINES = [
    {
        "timestamp": "2026-08-01T10:00:00+00:00",
        "provider": "OllamaProvider",
        "model": "llama3",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "latency_seconds": 0.5,
        "ok": True,
        "error": "",
    },
    {
        "timestamp": "2026-08-01T10:01:00+00:00",
        "provider": "OllamaProvider",
        "model": "llama3",
        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        "latency_seconds": 0.7,
        "ok": True,
        "error": "",
    },
    {
        "timestamp": "2026-08-01T10:02:00+00:00",
        "provider": "MockProvider",
        "model": "mock",
        "usage": {"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
        "latency_seconds": None,
        "ok": False,
        "error": "boom",
    },
]


def _write_jsonl(path: Path, records: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def _append_event(path: Path, event_id: str) -> None:
    """Append one event record to an events JSONL source."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "_type": "event",
                    "metadata": {
                        "event_id": event_id,
                        "timestamp": "2026-08-01T12:00:00+00:00",
                        "event_type": "audit.write",
                        "source": "api",
                        "status": "delivered",
                    },
                    "payload": {},
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def _append_metric(path: Path) -> None:
    """Append one runtime metrics snapshot line."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "timestamp": "2026-08-01T11:00:00+00:00",
                    "snapshot": {
                        "uptime_seconds": 30.0,
                        "gauges": {
                            "cpu_percent": 5.0,
                            "memory_percent": 42.0,
                            "engine_healthy": 6,
                            "engine_degraded": 0,
                            "engine_failed": 0,
                        },
                        "counters": {"jobs_executed": 7, "jobs_failed": 0},
                    },
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def _append_usage(path: Path) -> None:
    """Append one provider usage record."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "timestamp": "2026-08-01T10:03:00+00:00",
                    "provider": "OllamaProvider",
                    "model": "llama3",
                    "usage": {
                        "prompt_tokens": 5,
                        "completion_tokens": 5,
                        "total_tokens": 10,
                    },
                    "latency_seconds": 0.4,
                    "ok": True,
                    "error": "",
                },
                ensure_ascii=False,
            )
            + "\n"
        )


@pytest.fixture
def sources(tmp_path: Path) -> dict[str, Path]:
    return {
        "events_path": _write_jsonl(tmp_path / "events" / "store.jsonl", EVENT_LINES),
        "metrics_path": _write_jsonl(
            tmp_path / "runtime" / "metrics_history.jsonl", METRIC_LINES
        ),
        "provider_usage_path": _write_jsonl(
            tmp_path / "runtime" / "provider_usage.jsonl", USAGE_LINES
        ),
    }


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "runtime" / "dashboard.db"


# ── store ───────────────────────────────────────────────────────────────


class TestReadModelStore:
    def test_rebuild_imports_all_sources(
        self, sources: dict[str, Path], db_path: Path
    ) -> None:
        store = ReadModelStore(db_path=db_path)
        store.rebuild(**sources)
        stats = store.stats()
        assert stats["events"] == 3
        assert stats["metrics_history"] == 2
        assert stats["provider_usage"] == 3
        assert stats["schema_version"] == "1"
        assert stats["rebuilt_at"]
        store.close()

    def test_wal_mode_enabled(self, sources: dict[str, Path], db_path: Path) -> None:
        store = ReadModelStore(db_path=db_path)
        store.rebuild(**sources)
        assert store.stats()["wal"] is True
        store.close()

    def test_rebuild_is_idempotent_drops_old_rows(
        self, sources: dict[str, Path], db_path: Path
    ) -> None:
        store = ReadModelStore(db_path=db_path)
        store.rebuild(**sources)
        assert store.stats()["events"] == 3
        # Append a new event and rebuild: old rows are dropped, not merged.
        with sources["events_path"].open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "_type": "event",
                        "metadata": {
                            "event_id": "evt_4",
                            "timestamp": "2026-08-01T11:00:00+00:00",
                            "event_type": "workflow.failed",
                            "source": "orchestration",
                            "status": "delivered",
                        },
                        "payload": {},
                    }
                )
                + "\n"
            )
        store.rebuild(**sources)
        assert store.stats()["events"] == 4
        store.close()

    def test_recent_events_newest_first_and_filtered(
        self, sources: dict[str, Path], db_path: Path
    ) -> None:
        store = ReadModelStore(db_path=db_path)
        store.rebuild(**sources)
        all_events = store.recent_events(limit=10)
        assert [e["event_id"] for e in all_events] == ["evt_3", "evt_2", "evt_1"]
        assert all_events[0]["payload"] == {"decision_id": "d1"}
        filtered = store.recent_events(limit=10, event_type="workflow.started")
        assert [e["event_id"] for e in filtered] == ["evt_1"]
        store.close()

    def test_event_counts_by_type(
        self, sources: dict[str, Path], db_path: Path
    ) -> None:
        store = ReadModelStore(db_path=db_path)
        store.rebuild(**sources)
        counts = {
            row["event_type"]: row["count"] for row in store.event_counts_by_type()
        }
        assert counts == {
            "workflow.started": 1,
            "workflow.completed": 1,
            "decision.approved": 1,
        }
        store.close()

    def test_metrics_summary_matches_latest_snapshot(
        self, sources: dict[str, Path], db_path: Path
    ) -> None:
        store = ReadModelStore(db_path=db_path)
        store.rebuild(**sources)
        summary = store.metrics_summary()
        assert summary["samples"] == 2
        assert summary["last_timestamp"] == "2026-08-01T10:05:00+00:00"
        assert summary["trend"]["cpu_percent"] == 9.8
        assert summary["trend"]["jobs_failed"] == 1
        store.close()

    def test_provider_usage_by_model(
        self, sources: dict[str, Path], db_path: Path
    ) -> None:
        store = ReadModelStore(db_path=db_path)
        store.rebuild(**sources)
        summary = store.provider_usage_by_model()
        assert summary["records"] == 3
        by_model = {row["model"]: row for row in summary["models"]}
        llama = by_model["llama3"]
        assert llama["requests"] == 2
        assert llama["successes"] == 2
        assert llama["total_tokens"] == 45
        assert llama["avg_latency_seconds"] == 0.6
        mock = by_model["mock"]
        assert mock["errors"] == 1
        assert mock["avg_latency_seconds"] is None
        assert summary["totals"]["requests"] == 3
        assert summary["totals"]["errors"] == 1
        store.close()

    def test_missing_sources_yield_empty_projection(
        self, tmp_path: Path, db_path: Path
    ) -> None:
        store = ReadModelStore(db_path=db_path)
        result = store.rebuild(
            events_path=tmp_path / "nope.jsonl",
            metrics_path=tmp_path / "nope.jsonl",
            provider_usage_path=tmp_path / "nope.jsonl",
        )
        assert result["events"] == 0
        assert store.stats()["events"] == 0
        assert store.recent_events() == []
        assert store.metrics_summary()["samples"] == 0
        store.close()


# ── engine ──────────────────────────────────────────────────────────────


class TestReadModelEngine:
    def test_construction_rebuilds_projection(
        self, sources: dict[str, Path], tmp_path: Path
    ) -> None:
        engine = ReadModelEngine(
            db_path=tmp_path / "runtime" / "dashboard.db", **sources
        )
        stats = engine.stats()
        assert stats["events"] == 3
        assert stats["provider_usage"] == 3

    def test_health_reports_healthy_with_rows(
        self, sources: dict[str, Path], tmp_path: Path
    ) -> None:
        engine = ReadModelEngine(
            db_path=tmp_path / "runtime" / "dashboard.db", **sources
        )
        health = engine.health()
        assert health["status"] == "healthy"
        assert health["rows"] == 8  # 3 events + 2 metrics + 3 usage

    def test_directory_db_path_appends_dashboard_db(
        self, sources: dict[str, Path], tmp_path: Path
    ) -> None:
        # Mirrors the startup.yaml param `db_path: "@state_dir"` which passes
        # a directory (the runtime state_dir).
        engine = ReadModelEngine(db_path=tmp_path / "runtime", **sources)
        assert engine.db_path == tmp_path / "runtime" / "dashboard.db"
        assert engine.stats()["db_path"] == str(tmp_path / "runtime" / "dashboard.db")

    def test_restart_rebuilds(self, sources: dict[str, Path], tmp_path: Path) -> None:
        engine = ReadModelEngine(
            db_path=tmp_path / "runtime" / "dashboard.db", **sources
        )
        before = engine.stats()["events"]
        with sources["events_path"].open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "_type": "event",
                        "metadata": {
                            "event_id": "evt_9",
                            "timestamp": "2026-08-01T12:00:00+00:00",
                            "event_type": "audit.write",
                            "source": "api",
                            "status": "delivered",
                        },
                        "payload": {},
                    }
                )
                + "\n"
            )
        engine.restart()
        assert engine.stats()["events"] == before + 1
        assert engine.recent_events(limit=1)[0]["event_id"] == "evt_9"

    def test_read_passthroughs(self, sources: dict[str, Path], tmp_path: Path) -> None:
        engine = ReadModelEngine(
            db_path=tmp_path / "runtime" / "dashboard.db", **sources
        )
        assert engine.event_counts_by_type()
        assert engine.metrics_summary()["samples"] == 2
        assert engine.provider_usage_by_model()["records"] == 3


# ── incremental sync (T1 — live sessions) ───────────────────────────────


class TestReadModelSync:
    """sync_from_jsonl: watermark-based incremental import (T1)."""

    def test_sync_appends_rows_written_since_rebuild(
        self, sources: dict[str, Path], db_path: Path
    ) -> None:
        store = ReadModelStore(db_path=db_path)
        store.rebuild(**sources)

        _append_event(sources["events_path"], "evt_4")
        _append_metric(sources["metrics_path"])
        _append_usage(sources["provider_usage_path"])

        result = store.sync_from_jsonl(**sources)
        assert result["events_appended"] == 1
        assert result["metrics_appended"] == 1
        assert result["provider_usage_appended"] == 1
        assert result["events_reset"] is False
        assert result["metrics_reset"] is False

        stats = store.stats()
        assert stats["events"] == 4
        assert stats["metrics_history"] == 3
        assert stats["provider_usage"] == 4
        assert stats["last_sync_at"]
        assert store.recent_events(limit=1)[0]["event_id"] == "evt_4"
        store.close()

    def test_sync_is_idempotent_when_nothing_appended(
        self, sources: dict[str, Path], db_path: Path
    ) -> None:
        store = ReadModelStore(db_path=db_path)
        store.rebuild(**sources)

        first = store.sync_from_jsonl(**sources)
        assert first["events_appended"] == 0
        assert first["metrics_appended"] == 0

        second = store.sync_from_jsonl(**sources)
        assert second["events_appended"] == 0
        assert second["metrics_appended"] == 0

        stats = store.stats()
        assert stats["events"] == 3
        assert stats["metrics_history"] == 2
        assert stats["provider_usage"] == 3
        store.close()

    def test_sync_full_imports_when_never_rebuilt(
        self, sources: dict[str, Path], db_path: Path
    ) -> None:
        # A fresh store (schema only, never rebuilt): watermarks are absent,
        # so the first sync fully imports every source.
        store = ReadModelStore(db_path=db_path)
        result = store.sync_from_jsonl(**sources)
        assert result["metrics_reset"] is True
        assert store.stats()["events"] == 3
        assert store.stats()["metrics_history"] == 2
        assert store.stats()["provider_usage"] == 3
        store.close()

    def test_sync_mirrors_source_after_truncation(
        self, sources: dict[str, Path], db_path: Path
    ) -> None:
        store = ReadModelStore(db_path=db_path)
        store.rebuild(**sources)
        _append_metric(sources["metrics_path"])
        store.sync_from_jsonl(**sources)
        assert store.stats()["metrics_history"] == 3

        # Truncate + rewrite the source (rotation/retention): the projection
        # drops the stale rows and mirrors the source exactly.
        _write_jsonl(sources["metrics_path"], METRIC_LINES[:1])
        result = store.sync_from_jsonl(**sources)
        assert result["metrics_reset"] is True
        assert store.stats()["metrics_history"] == 1
        assert store.metrics_summary()["samples"] == 1
        store.close()

    def test_sync_dedupes_events_by_id(
        self, sources: dict[str, Path], db_path: Path
    ) -> None:
        store = ReadModelStore(db_path=db_path)
        store.rebuild(**sources)

        # Duplicate of an already-imported event_id: parsed, but the primary
        # key ignores it — no duplicates in the projection.
        _append_event(sources["events_path"], "evt_1")
        result = store.sync_from_jsonl(**sources)
        assert result["events_appended"] == 1
        assert store.stats()["events"] == 3
        store.close()

    def test_sync_missing_sources_is_a_noop(
        self, tmp_path: Path, db_path: Path
    ) -> None:
        store = ReadModelStore(db_path=db_path)
        store.rebuild(
            events_path=tmp_path / "nope.jsonl",
            metrics_path=tmp_path / "nope.jsonl",
            provider_usage_path=tmp_path / "nope.jsonl",
        )
        result = store.sync_from_jsonl(
            events_path=tmp_path / "nope.jsonl",
            metrics_path=tmp_path / "nope.jsonl",
            provider_usage_path=tmp_path / "nope.jsonl",
        )
        assert result["events_appended"] == 0
        assert result["metrics_appended"] == 0
        assert result["provider_usage_appended"] == 0
        assert store.stats()["events"] == 0
        assert store.stats()["metrics_history"] == 0
        store.close()


class TestReadModelEngineSync:
    def test_engine_sync_appends_rows(
        self, sources: dict[str, Path], tmp_path: Path
    ) -> None:
        engine = ReadModelEngine(
            db_path=tmp_path / "runtime" / "dashboard.db", **sources
        )
        _append_event(sources["events_path"], "evt_10")
        _append_usage(sources["provider_usage_path"])

        result = engine.sync()
        assert result["events_appended"] == 1
        assert result["provider_usage_appended"] == 1
        assert engine.stats()["events"] == 4
        assert engine.stats()["provider_usage"] == 4
        assert engine.recent_events(limit=1)[0]["event_id"] == "evt_10"
