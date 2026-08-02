"""Integration tests: full runtime boot against the repo runtime config."""

from __future__ import annotations

import time

import pytest

from ai_company.runtime import create_runtime
from ai_company.runtime.models import HealthStatus, RuntimePhase


@pytest.fixture
def runtime():
    engine = create_runtime(config_dir="config")
    yield engine
    try:
        status = engine.status()
        if status is not None and status.phase.value == "running":
            engine.stop(reason="test-teardown")
    except Exception:
        pass


def test_runtime_boots_end_to_end(runtime) -> None:
    status = runtime.start()
    assert status.phase is RuntimePhase.RUNNING
    assert runtime.startup_sequence.success is True
    assert len(runtime.startup_sequence.steps) == 11


def test_all_core_engines_registered(runtime) -> None:
    runtime.start()
    names = set(runtime.engines)
    assert {
        "memory",
        "event_bus",
        "decision",
        "workflow",
        "orchestration",
        "read_model",
    } <= names


def test_scheduler_jobs_loaded_from_config(runtime) -> None:
    runtime.start()
    jobs = runtime.scheduler.jobs()
    assert len(jobs) == 5
    names = {job.name for job in jobs}
    assert "Daily executive briefing" in names
    assert "Continuous memory consolidation" in names


def test_health_all_green_after_boot(runtime) -> None:
    runtime.start()
    checks = runtime.health()
    components = {check.component for check in checks}
    assert {
        "memory",
        "event_bus",
        "decision",
        "workflow",
        "orchestration",
        "read_model",
        "system",
    } <= components
    assert all(check.status is HealthStatus.HEALTHY for check in checks)


def test_metrics_reflect_running_engines(runtime) -> None:
    runtime.start()
    metrics = runtime.metrics()
    assert metrics.active_engines == 6
    assert metrics.engine_healthy == 6
    assert metrics.queue_sizes.get("pending", 0) == 5
    assert metrics.counters.get("starts", 0) >= 1


def test_diagnostics_report_complete(runtime) -> None:
    runtime.start()
    report = runtime.diagnostics()
    assert len(report.errors) == 0
    assert report.phase is RuntimePhase.RUNNING
    assert len(report.config_sections) == 8
    assert len(report.engines) == 6


def test_runtime_stops_cleanly(runtime) -> None:
    runtime.start()
    status = runtime.stop(reason="test")
    assert status.phase is RuntimePhase.STOPPED
    assert runtime.shutdown_sequence.success is True
    # all workers stopped
    assert runtime.scheduler.is_running() is False
    assert runtime.watchdog.is_running() is False
    assert runtime.supervisor.is_running() is False
    assert runtime.heartbeat_sender.is_running() is False


def test_state_recovered_across_boot(runtime) -> None:
    runtime.start()
    runtime.state_store.add_active("pipelines", "p_recovery_test")
    runtime.stop(reason="test")

    second = create_runtime(config_dir="config")
    try:
        second.start()
        state = second.state_store.load()
        assert "p_recovery_test" in state.active_pipelines
    finally:
        try:
            second.stop(reason="test-teardown")
        except Exception:
            pass


def test_job_execution_via_tick(runtime) -> None:
    runtime.start()
    executed_before = runtime.scheduler.executed_count()
    # "Quarterly strategy review" fires at 11:00 on Jan/Apr/Jul/Oct 1.
    # Force one job to run by calling run_now with a directly-registered job.
    ran: list[str] = []
    runtime.submit_job(
        name="smoke-once",
        kind="one_time",
        handler=lambda job, rt: ran.append(job.name),
    )
    assert runtime.scheduler.run_now("smoke-once") is True
    assert ran == ["smoke-once"]
    assert runtime.scheduler.executed_count() >= executed_before


def test_heartbeats_tracked_for_engines(runtime) -> None:
    runtime.start()
    components = set(runtime.heartbeats.components())
    assert {
        "memory",
        "event_bus",
        "decision",
        "workflow",
        "orchestration",
    } <= components


def test_engines_stay_healthy_and_not_isolated_after_boot(runtime) -> None:
    """Regression: engines were heartbeat-timeouted and isolated after boot.

    The heartbeat sender must keep every engine fresh past the 15s
    staleness window and the read_model health probe must succeed from the
    health-monitor thread (SQLite check_same_thread). No engine may be
    flagged for recovery or isolated after a full heartbeat window.
    """
    runtime.start()
    for _ in range(10):  # poll every 2s for 20s; fail fast on isolation
        assert runtime.supervisor.isolated() == []
        time.sleep(2)
    assert runtime.heartbeats.heartbeat_miss_count() == 0
    checks = runtime.health()
    assert all(check.status is HealthStatus.HEALTHY for check in checks)
    assert runtime.recovery.snapshot()["attempts"] == {}


def test_runtime_restart_keeps_engines_and_jobs(runtime) -> None:
    runtime.start()
    runtime.restart(reason="test-restart")
    assert runtime.status().phase is RuntimePhase.RUNNING
    assert len(runtime.scheduler.jobs()) == 5
    assert len(runtime.engines) == 6
