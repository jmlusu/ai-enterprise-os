"""Unit tests for the runtime watchdog."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ai_company.runtime.heartbeat import HeartbeatManager
from ai_company.runtime.watchdog import Watchdog


def test_track_and_untrack_task() -> None:
    watchdog = Watchdog(settings={})
    watchdog.track_task("task-1", deadline_seconds=10.0)
    assert watchdog.tracked_tasks() == ["task-1"]
    watchdog.untrack_task("task-1")
    assert watchdog.tracked_tasks() == []


def test_task_overrun() -> None:
    watchdog = Watchdog(settings={})
    watchdog.track_task("task-1", deadline_seconds=1.0)
    now = datetime.now(UTC)
    assert not watchdog.task_overrun("task-1", now=now)
    assert watchdog.task_overrun("task-1", now=now + timedelta(seconds=2))
    # unknown tasks never overrun
    assert not watchdog.task_overrun("missing", now=now + timedelta(seconds=99))


def test_check_reports_deadline_exceeded() -> None:
    fired: list[tuple[str, str]] = []
    watchdog = Watchdog(
        settings={"task_deadline_seconds": 1.0},
        on_failure=lambda component, reason: fired.append((component, reason)),
    )
    watchdog.track_task("task-1", deadline_seconds=1.0)
    failures = watchdog.check(now=datetime.now(UTC) + timedelta(seconds=5))
    assert ("task-1", "deadline_exceeded") in failures
    assert ("task-1", "deadline_exceeded") in fired
    # the overrun task is untracked after being reported
    assert watchdog.tracked_tasks() == []


def test_check_forwards_heartbeat_failures() -> None:
    heartbeats = HeartbeatManager(
        settings={"timeout_seconds": 0.001, "missed_beats_before_failure": 1}
    )
    heartbeats.register("engine-a")
    watchdog = Watchdog(settings={}, heartbeats=heartbeats)
    failures = watchdog.check(now=datetime.now(UTC) + timedelta(seconds=5))
    assert ("engine-a", "heartbeat_timeout") in failures


def test_start_stop_roundtrip() -> None:
    watchdog = Watchdog(settings={"watchdog_interval_seconds": 0.05})
    watchdog.start()
    assert watchdog.is_running()
    watchdog.stop()
    assert not watchdog.is_running()


def test_disabled_watchdog_does_not_start() -> None:
    watchdog = Watchdog(settings={"watchdog_enabled": False})
    watchdog.start()
    assert not watchdog.is_running()


def test_snapshot() -> None:
    watchdog = Watchdog(settings={})
    watchdog.track_task("task-1")
    snapshot = watchdog.snapshot()
    assert snapshot["tracked_tasks"] == 1
    assert snapshot["enabled"] is True
