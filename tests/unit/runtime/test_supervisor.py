"""Unit tests for the runtime supervisor."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_company.events.models import EventType
from ai_company.runtime.health import HealthMonitor
from ai_company.runtime.heartbeat import HeartbeatManager
from ai_company.runtime.models import RecoveryResult
from ai_company.runtime.recovery import RecoveryManager
from ai_company.runtime.supervisor import Supervisor
from ai_company.telemetry import alerts as alerts_module
from ai_company.telemetry.alerts import alerts_summary


class _CapturingBus:
    """Fake event bus that records published events."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def publish_event(self, **kwargs) -> None:
        self.events.append(kwargs)


@pytest.fixture()
def alerts_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the alerts log at a tmp file for a hermetic test."""
    target = tmp_path / "alerts.jsonl"
    monkeypatch.setattr(alerts_module, "alerts_path", lambda: target)
    return target


class _FlakyEngine:
    def health(self) -> dict:
        return {"status": "unhealthy", "error": "flaky"}


class _StableEngine:
    def health(self) -> dict:
        return {"status": "healthy"}


def _recovery_manager(restart_ok: bool = True) -> RecoveryManager:
    if restart_ok:
        return RecoveryManager(
            config={"policies": {"engine-*": {"actions": ["restart"]}}}
        )
    return RecoveryManager(config={"policies": {"engine-*": {"actions": ["teleport"]}}})


def test_on_failure_recovers_component() -> None:
    recovery = _recovery_manager()
    recovery.register_factory("engine-a", lambda: None)
    supervisor = Supervisor(recovery=recovery)
    supervisor.on_failure("engine-a", "heartbeat_timeout")
    assert recovery.attempts("engine-a") == 1
    assert supervisor.recent_failures() != {}


def test_failed_recovery_isolates_component() -> None:
    recovery = _recovery_manager(restart_ok=False)
    supervisor = Supervisor(recovery=recovery)
    supervisor.on_failure("engine-a", "heartbeat_timeout")
    assert supervisor.isolated() == ["engine-a"]


def test_isolated_component_ignores_failures() -> None:
    recovery = _recovery_manager(restart_ok=False)
    supervisor = Supervisor(recovery=recovery)
    supervisor.on_failure("engine-a", "first")
    attempts_before = recovery.attempts("engine-a")
    supervisor.on_failure("engine-a", "second")
    assert recovery.attempts("engine-a") == attempts_before


def test_unisolate_resets_attempts() -> None:
    recovery = _recovery_manager()
    recovery.register_factory("engine-a", lambda: None)
    supervisor = Supervisor(recovery=recovery)
    supervisor.on_failure("engine-a", "test")
    supervisor.isolate("engine-a", "manual")
    supervisor.unisolate("engine-a")
    assert supervisor.isolated() == []
    assert recovery.attempts("engine-a") == 0


def test_check_once_detects_unhealthy_engine() -> None:
    health = HealthMonitor()
    health.register("engine-a", _FlakyEngine())
    recovery = _recovery_manager()
    recovery.register_factory("engine-a", lambda: None)
    supervisor = Supervisor(health=health, recovery=recovery)
    failures = supervisor.check_once()
    assert "engine-a" in failures


def test_check_once_detects_stale_heartbeat() -> None:
    heartbeats = HeartbeatManager(
        settings={"timeout_seconds": 0.001, "missed_beats_before_failure": 1}
    )
    heartbeats.register("engine-a")
    recovery = _recovery_manager()
    recovery.register_factory("engine-a", lambda: None)
    supervisor = Supervisor(heartbeats=heartbeats, recovery=recovery)
    failures = supervisor.check_once(now=datetime.now(UTC) + timedelta(seconds=5))
    assert "engine-a" in failures


def test_healthy_system_no_failures() -> None:
    health = HealthMonitor()
    health.register("engine-a", _StableEngine())
    supervisor = Supervisor(health=health)
    assert supervisor.check_once() == []


def test_start_stop_roundtrip() -> None:
    supervisor = Supervisor(config={"check_interval_seconds": 0.05})
    supervisor.start()
    assert supervisor.is_running()
    supervisor.stop()
    assert not supervisor.is_running()


def test_on_engine_failed_callback() -> None:
    captured: list[tuple[str, str, RecoveryResult]] = []
    recovery = _recovery_manager()
    recovery.register_factory("engine-a", lambda: None)
    supervisor = Supervisor(
        recovery=recovery,
        on_engine_failed=lambda name, reason, result: captured.append(
            (name, reason, result)
        ),
    )
    supervisor.on_failure("engine-a", "boom")
    assert captured and captured[0][0] == "engine-a"
    assert captured[0][1] == "boom"


def test_snapshot() -> None:
    supervisor = Supervisor()
    snapshot = supervisor.snapshot()
    assert snapshot["running"] is False
    assert snapshot["isolated"] == []


# ── T3 isolation alerting ────────────────────────────────────────────────


def test_isolate_records_open_alert(alerts_file: Path) -> None:
    supervisor = Supervisor()
    supervisor.isolate("engine-a", reason="heartbeat_timeout", attempts=2)
    summary = alerts_summary()
    assert summary["open_count"] == 1
    alert = summary["open_alerts"][0]
    assert alert["component"] == "engine-a"
    assert alert["reason"] == "heartbeat_timeout"
    assert alert["attempts"] == 2


def test_unisolate_resolves_open_alert(alerts_file: Path) -> None:
    supervisor = Supervisor()
    supervisor.isolate("engine-a", reason="manual")
    supervisor.unisolate("engine-a")
    summary = alerts_summary()
    assert summary["open_count"] == 0
    assert summary["open_alerts"] == []


def test_failed_recovery_records_alert_with_attempts(alerts_file: Path) -> None:
    recovery = _recovery_manager(restart_ok=False)
    supervisor = Supervisor(recovery=recovery)
    supervisor.on_failure("engine-a", "heartbeat_timeout")
    assert supervisor.isolated() == ["engine-a"]
    summary = alerts_summary()
    assert summary["open_count"] == 1
    assert summary["open_alerts"][0]["component"] == "engine-a"
    assert summary["open_alerts"][0]["reason"] == "recovery failed: heartbeat_timeout"


def test_isolate_publishes_engine_isolated_event() -> None:
    bus = _CapturingBus()
    supervisor = Supervisor(event_bus=bus)
    supervisor.isolate("engine-a", reason="manual", attempts=3)
    assert any(
        e.get("event_type") == EventType.SYSTEM_ERROR
        and e.get("payload", {}).get("runtime_event_type") == "runtime.engine_isolated"
        and e.get("payload", {}).get("component") == "engine-a"
        and e.get("payload", {}).get("attempts") == 3
        and e.get("source") == "runtime.supervisor"
        for e in bus.events
    )


def test_unisolate_publishes_engine_unisolated_event() -> None:
    bus = _CapturingBus()
    supervisor = Supervisor(event_bus=bus)
    supervisor.isolate("engine-a", reason="manual")
    supervisor.unisolate("engine-a")
    assert any(
        e.get("event_type") == EventType.SYSTEM_HEALTH_CHECK
        and e.get("payload", {}).get("runtime_event_type")
        == "runtime.engine_unisolated"
        and e.get("payload", {}).get("component") == "engine-a"
        for e in bus.events
    )
