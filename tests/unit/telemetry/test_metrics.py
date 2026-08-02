"""Unit tests for runtime metrics persistence (risk R5)."""

from __future__ import annotations

from typing import Any

import pytest

from ai_company.telemetry.metrics import (
    log_metrics_snapshot,
    metrics_summary,
    read_metrics_history,
)


@pytest.fixture(autouse=True)
def _isolated_history(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the metrics history log at a temp file per test."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "runtime" / "metrics_history.jsonl"
    monkeypatch.setattr(
        "ai_company.telemetry.metrics.METRICS_HISTORY_RELATIVE_PATH",
        target.relative_to(tmp_path),
    )


def _snapshot() -> dict[str, Any]:
    return {
        "uptime_seconds": 120.0,
        "gauges": {
            "cpu_percent": 12.5,
            "memory_percent": 41.0,
            "engine_healthy": 8,
            "engine_degraded": 1,
            "engine_failed": 0,
        },
        "counters": {
            "jobs_executed": 42,
            "jobs_failed": 1,
            "failed_events": 0,
            "restarts": 0,
        },
    }


def test_metrics_history_append_and_read(tmp_path: Any) -> None:
    log_metrics_snapshot(_snapshot())
    log_metrics_snapshot({"uptime_seconds": 240.0, "gauges": {}, "counters": {}})
    records = read_metrics_history()
    assert len(records) == 2
    assert records[0]["snapshot"]["uptime_seconds"] == 120.0
    assert records[1]["timestamp"] > records[0]["timestamp"]


def test_metrics_summary_derives_trend(tmp_path: Any) -> None:
    log_metrics_snapshot(_snapshot())
    summary = metrics_summary()
    assert summary["persistence_enabled"] is True
    assert summary["samples"] == 1
    trend = summary["trend"]
    assert trend["cpu_percent"] == 12.5
    assert trend["memory_percent"] == 41.0
    assert trend["engine_healthy"] == 8
    assert trend["jobs_executed"] == 42


def test_metrics_summary_empty_when_no_history(tmp_path: Any) -> None:
    summary = metrics_summary()
    assert summary["samples"] == 0
    assert summary["latest"] is None


def test_metrics_history_skips_corrupt_lines(tmp_path: Any) -> None:
    target = tmp_path / "runtime" / "metrics_history.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("not-json\n", encoding="utf-8")
    log_metrics_snapshot(_snapshot())
    records = read_metrics_history()
    assert len(records) == 1


def test_metrics_persistence_never_raises(tmp_path: Any) -> None:
    # A snapshot with unserializable content must not raise (fail-open).
    log_metrics_snapshot({"weird": object()})  # type: ignore[dict-item]
    assert read_metrics_history() == []
