"""Unit tests for the runtime health monitor."""

from __future__ import annotations

from ai_company.runtime.health import HealthMonitor
from ai_company.runtime.models import HealthStatus


class _HealthyEngine:
    def health(self) -> dict:
        return {"status": "healthy", "uptime": 10}


class _DegradedEngine:
    def health(self) -> dict:
        return {"status": "degraded", "reason": "busy"}


class _BrokenEngine:
    def health(self) -> dict:
        raise RuntimeError("probe exploded")


class _PassiveEngine:
    """No health() method — assumed healthy."""


class _DictReturningEngine:
    def health(self) -> dict:
        return {"status": "ok", "load": 0.5}


def test_healthy_probe() -> None:
    monitor = HealthMonitor()
    monitor.register("engine", _HealthyEngine())
    checks = monitor.check_all()
    engine_check = next(c for c in checks if c.component == "engine")
    assert engine_check.status is HealthStatus.HEALTHY
    assert engine_check.details == {"uptime": 10}


def test_degraded_probe() -> None:
    monitor = HealthMonitor()
    monitor.register("engine", _DegradedEngine())
    checks = monitor.check_all()
    engine_check = next(c for c in checks if c.component == "engine")
    assert engine_check.status is HealthStatus.DEGRADED


def test_exception_maps_to_unhealthy() -> None:
    monitor = HealthMonitor()
    monitor.register("engine", _BrokenEngine())
    checks = monitor.check_all()
    engine_check = next(c for c in checks if c.component == "engine")
    assert engine_check.status is HealthStatus.UNHEALTHY
    assert "probe exploded" in (engine_check.error or "")


def test_passive_component_is_healthy() -> None:
    monitor = HealthMonitor()
    monitor.register("engine", _PassiveEngine())
    checks = monitor.check_all()
    engine_check = next(c for c in checks if c.component == "engine")
    assert engine_check.status is HealthStatus.HEALTHY


def test_ok_status_normalized_to_healthy() -> None:
    monitor = HealthMonitor()
    monitor.register("engine", _DictReturningEngine())
    checks = monitor.check_all()
    engine_check = next(c for c in checks if c.component == "engine")
    assert engine_check.status is HealthStatus.HEALTHY


def test_system_check_present() -> None:
    monitor = HealthMonitor()
    checks = monitor.check_all()
    assert any(c.component == "system" for c in checks)


def test_aggregate_worst_status() -> None:
    monitor = HealthMonitor()
    monitor.register("healthy", _HealthyEngine())
    monitor.register("broken", _BrokenEngine())
    assert monitor.aggregate() is HealthStatus.UNHEALTHY


def test_summary_counts() -> None:
    monitor = HealthMonitor()
    monitor.register("healthy", _HealthyEngine())
    monitor.register("degraded", _DegradedEngine())
    monitor.register("broken", _BrokenEngine())
    summary = monitor.summary()
    assert summary["healthy"] >= 1
    assert summary["degraded"] == 1
    assert summary["unhealthy"] == 1
    assert summary["status"] == "unhealthy"


def test_unregister() -> None:
    monitor = HealthMonitor()
    monitor.register("engine", _HealthyEngine())
    assert monitor.unregister("engine") is True
    assert monitor.unregister("engine") is False
    assert monitor.components() == []


def test_custom_probe_override() -> None:
    monitor = HealthMonitor(
        probe=lambda name, component: {"status": "unhealthy", "error": "custom"}
    )
    monitor.register("engine", _HealthyEngine())
    checks = monitor.check_all()
    engine_check = next(c for c in checks if c.component == "engine")
    assert engine_check.status is HealthStatus.UNHEALTHY
