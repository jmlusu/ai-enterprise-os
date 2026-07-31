"""Unit tests for the runtime heartbeat manager."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ai_company.runtime.heartbeat import HeartbeatManager
from ai_company.runtime.models import HealthStatus


def test_register_and_beat() -> None:
    manager = HeartbeatManager()
    manager.register("engine-a")
    heartbeat = manager.beat("engine-a")
    assert heartbeat.seq == 1
    assert heartbeat.component == "engine-a"
    assert manager.components() == ["engine-a"]


def test_beat_resets_consecutive_misses() -> None:
    manager = HeartbeatManager(
        settings={"timeout_seconds": 0.001, "missed_beats_before_failure": 1}
    )
    manager.register("engine-a")
    failures = manager.check(now=datetime.now(UTC) + timedelta(seconds=5))
    assert failures == [("engine-a", "heartbeat_timeout")]
    assert manager.consecutive_misses("engine-a") == 0
    manager.beat("engine-a")
    assert manager.consecutive_misses("engine-a") == 0


def test_stale_detection() -> None:
    manager = HeartbeatManager(settings={"timeout_seconds": 10.0})
    manager.register("engine-a")
    now = datetime.now(UTC)
    assert not manager.is_stale("engine-a", now=now)
    assert manager.is_stale("engine-a", now=now + timedelta(seconds=11))


def test_missed_threshold_triggers_callback() -> None:
    fired: list[tuple[str, str]] = []
    manager = HeartbeatManager(
        settings={"timeout_seconds": 0.001, "missed_beats_before_failure": 2},
        on_failure=lambda component, reason: fired.append((component, reason)),
    )
    manager.register("engine-a")
    now = datetime.now(UTC)
    manager.check(now=now + timedelta(seconds=5))  # miss 1 — no fire
    assert fired == []
    manager.check(now=now + timedelta(seconds=10))  # miss 2 — fire
    assert ("engine-a", "heartbeat_timeout") in fired


def test_unregister() -> None:
    manager = HeartbeatManager()
    manager.register("engine-a")
    assert manager.unregister("engine-a") is True
    assert manager.unregister("engine-a") is False
    assert manager.components() == []


def test_seconds_since_unknown_is_inf() -> None:
    manager = HeartbeatManager()
    assert manager.seconds_since("missing") == float("inf")


def test_heartbeat_status_payload() -> None:
    manager = HeartbeatManager()
    heartbeat = manager.beat("engine-a", status=HealthStatus.DEGRADED, payload={"x": 1})
    assert heartbeat.status is HealthStatus.DEGRADED
    assert heartbeat.payload == {"x": 1}


def test_snapshot() -> None:
    manager = HeartbeatManager()
    manager.register("engine-a")
    snapshot = manager.snapshot()
    assert snapshot["monitored"] == 1
    assert "engine-a" in snapshot["components"]


def test_interval_override_per_component() -> None:
    manager = HeartbeatManager(settings={"interval_seconds": 5.0})
    heartbeat = manager.register("engine-a", interval_seconds=1.0)
    assert heartbeat.interval_seconds == 1.0
