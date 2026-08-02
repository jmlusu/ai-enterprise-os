"""Unit tests for the isolation alerts telemetry module (sprint 5.4 T3).

Covers the no-spam contract: the latest record per component wins, so
repeated isolates collapse to one open alert until a ``resolved`` record
supersedes it. All reads/writes are fail-open and never raise.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_company.telemetry import alerts
from ai_company.telemetry.alerts import (
    alerts_summary,
    read_alerts,
    record_alert_open,
    record_alert_resolved,
)


@pytest.fixture()
def alerts_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the alerts log at a tmp file for a hermetic test."""
    target = tmp_path / "alerts.jsonl"
    monkeypatch.setattr(alerts, "alerts_path", lambda: target)
    return target


def _open(component: str, reason: str = "boom", attempts: int | None = None) -> None:
    record_alert_open(component=component, reason=reason, attempts=attempts)


def test_empty_summary(alerts_file: Path) -> None:
    summary = alerts_summary()
    assert summary["persistence_enabled"] is True
    assert summary["records"] == 0
    assert summary["open_count"] == 0
    assert summary["open_alerts"] == []
    assert summary["recent"] == []


def test_open_alert_roundtrip(alerts_file: Path) -> None:
    _open("engine-a", reason="heartbeat_timeout", attempts=3)
    summary = alerts_summary()
    assert summary["records"] == 1
    assert summary["open_count"] == 1
    alert = summary["open_alerts"][0]
    assert alert["component"] == "engine-a"
    assert alert["reason"] == "heartbeat_timeout"
    assert alert["attempts"] == 3
    assert alert["opened_at"]
    assert alert["source"] == "runtime.supervisor"


def test_repeated_isolates_collapse_to_one_open(alerts_file: Path) -> None:
    """No-spam contract: many isolates of the same component = one open alert."""
    _open("engine-a", reason="first")
    _open("engine-a", reason="second")
    _open("engine-a", reason="third", attempts=3)
    summary = alerts_summary()
    assert summary["open_count"] == 1
    assert len(summary["open_alerts"]) == 1
    # Latest record wins (reason/attempts reflect the newest isolate).
    assert summary["open_alerts"][0]["reason"] == "third"
    assert summary["open_alerts"][0]["attempts"] == 3
    # The full tail is preserved for the recent feed.
    assert summary["records"] == 3


def test_resolution_clears_open_alert(alerts_file: Path) -> None:
    _open("engine-a", reason="heartbeat_timeout", attempts=2)
    record_alert_resolved(component="engine-a", reason="unisolated")
    summary = alerts_summary()
    assert summary["open_count"] == 0
    assert summary["open_alerts"] == []
    # The resolved record is part of the recent tail.
    assert summary["recent"][-1]["kind"] == "resolved"
    assert summary["records"] == 2


def test_open_after_resolution_reopens(alerts_file: Path) -> None:
    _open("engine-a", reason="first")
    record_alert_resolved(component="engine-a")
    _open("engine-a", reason="second", attempts=1)
    summary = alerts_summary()
    assert summary["open_count"] == 1
    assert summary["open_alerts"][0]["reason"] == "second"


def test_multiple_components_independent(alerts_file: Path) -> None:
    _open("engine-a", reason="stale")
    _open("engine-b", reason="unhealthy")
    record_alert_resolved(component="engine-a")
    summary = alerts_summary()
    assert summary["open_count"] == 1
    assert [a["component"] for a in summary["open_alerts"]] == ["engine-b"]


def test_corrupt_line_skipped(alerts_file: Path) -> None:
    alerts_file.write_text(
        json.dumps(
            {
                "timestamp": "2026-08-02T00:00:00+00:00",
                "kind": "open",
                "component": "engine-a",
                "reason": "ok",
                "attempts": None,
                "source": "runtime.supervisor",
            }
        )
        + "\n{not valid json\n",
        encoding="utf-8",
    )
    summary = alerts_summary()
    assert summary["open_count"] == 1
    assert summary["records"] == 1


def test_limit_tails_read(alerts_file: Path) -> None:
    for i in range(5):
        _open(f"engine-{i}", reason=f"r{i}")
    assert len(read_alerts(limit=2)) == 2
    summary = alerts_summary(limit=3)
    assert summary["records"] == 3


def test_fail_open_missing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A missing log never raises and reads as empty."""
    monkeypatch.setattr(
        alerts, "alerts_path", lambda: tmp_path / "does-not-exist.jsonl"
    )
    assert alerts_summary()["open_count"] == 0
    assert read_alerts() == []


def test_write_fail_open_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Record helpers never raise even when the write path is broken."""

    def _broken() -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(alerts, "alerts_path", _broken)
    record_alert_open(component="engine-a", reason="boom")  # must not raise
    record_alert_resolved(component="engine-a")  # must not raise
