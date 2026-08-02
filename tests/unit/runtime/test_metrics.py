"""Unit tests for the runtime metrics registry."""

from __future__ import annotations

import time

from ai_company.runtime.metrics import MetricsRegistry


def test_counter_increment_and_decrement() -> None:
    registry = MetricsRegistry()
    assert registry.increment("jobs", 2) == 2.0
    assert registry.increment("jobs") == 3.0
    assert registry.decrement("jobs") == 2.0
    assert registry.counter("jobs") == 2.0
    assert registry.counter("missing") == 0.0


def test_gauge_float_and_dict() -> None:
    registry = MetricsRegistry()
    registry.set_gauge("active_engines", 3)
    assert registry.gauge("active_engines") == 3.0
    registry.set_gauge("queue_sizes", {"pending": 5, "completed": 2})
    assert registry.gauge("queue_sizes") == {"pending": 5, "completed": 2}


def test_timed_context_manager() -> None:
    registry = MetricsRegistry()
    # Windows monotonic clock resolution can coarsen short measurements;
    # use a 50ms sleep and a tolerant lower bound to avoid flakes (Phase 0).
    with registry.timed("op"):
        time.sleep(0.05)
    assert registry.timer("op") >= 0.04
    assert registry.timers()["op"] >= 0.04


def test_record_timer_accumulates() -> None:
    registry = MetricsRegistry()
    registry.record_timer("op", 1.0)
    registry.record_timer("op", 2.0)
    assert registry.timer("op") == 3.0


def test_uptime_increases() -> None:
    registry = MetricsRegistry()
    first = registry.uptime_seconds()
    time.sleep(0.01)
    assert registry.uptime_seconds() >= first


def test_snapshot_shape() -> None:
    registry = MetricsRegistry()
    registry.increment("jobs")
    registry.set_gauge("active_engines", 1)
    snapshot = registry.snapshot()
    assert snapshot["counters"]["jobs"] == 1.0
    assert snapshot["gauges"]["active_engines"] == 1.0
    assert "uptime_seconds" in snapshot


def test_to_metrics_maps_fields() -> None:
    registry = MetricsRegistry()
    registry.increment("jobs_executed", 4)
    registry.increment("jobs_failed", 1)
    registry.increment("failed_events", 2)
    registry.increment("recovery_attempts", 5)
    registry.increment("recovery_successes", 3)
    registry.increment("recovery_failures", 2)
    registry.set_gauge("recovery_success_rate", 60.0)
    registry.set_gauge("active_engines", 5)
    registry.set_gauge("engine_healthy", 5)
    registry.set_gauge("queue_sizes", {"pending": 2})
    metrics = registry.to_metrics()
    assert metrics.jobs_executed == 4
    assert metrics.jobs_failed == 1
    assert metrics.failed_events == 2
    assert metrics.active_engines == 5
    assert metrics.engine_healthy == 5
    assert metrics.queue_sizes == {"pending": 2}
    # T4 — recovery-outcome fields map through to RuntimeMetrics.
    assert metrics.recovery_attempts == 5
    assert metrics.recovery_successes == 3
    assert metrics.recovery_failures == 2
    assert metrics.recovery_success_rate == 60.0


def test_to_metrics_recovery_defaults_to_zero() -> None:
    registry = MetricsRegistry()
    metrics = registry.to_metrics()
    assert metrics.recovery_attempts == 0
    assert metrics.recovery_successes == 0
    assert metrics.recovery_failures == 0
    assert metrics.recovery_success_rate == 0.0


def test_reset_clears_everything() -> None:
    registry = MetricsRegistry()
    registry.increment("jobs")
    registry.set_gauge("active_engines", 1)
    registry.record_timer("op", 1.0)
    registry.reset()
    assert registry.counters() == {}
    assert registry.gauges() == {}
    assert registry.timers() == {}
