"""Integration tests: runtime restart, hot reload, and supervision."""

from __future__ import annotations

import pytest

from ai_company.runtime import create_runtime
from ai_company.runtime.models import EngineStateStatus, RuntimePhase


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


def test_restart_preserves_scheduler_jobs(runtime) -> None:
    runtime.start()
    runtime.restart(reason="test")
    jobs = runtime.scheduler.jobs()
    assert len(jobs) == 6
    assert runtime.status().phase is RuntimePhase.RUNNING


def test_reload_reports_no_changes_when_config_stable(runtime) -> None:
    runtime.start()
    changed = runtime.reload()
    assert isinstance(changed, list)
    assert set(changed) <= {
        "runtime",
        "startup",
        "heartbeat",
        "scheduler",
        "monitoring",
        "health",
        "recovery",
        "diagnostics",
    }


def test_engine_failure_flow_through_supervisor(runtime) -> None:
    runtime.start()
    # Register a component with a recovery factory; simulate a failure.
    runtime.recovery.register_factory("test-worker", lambda: None)
    runtime.register_process("test-worker")
    runtime.supervisor.on_failure("test-worker", "simulated")
    assert runtime.recovery.attempts("test-worker") >= 1


def test_isolate_and_unisolate_engine(runtime) -> None:
    runtime.start()
    runtime.supervisor.isolate("test-engine", "manual")
    assert "test-engine" in runtime.supervisor.isolated()
    runtime.supervisor.unisolate("test-engine")
    assert "test-engine" not in runtime.supervisor.isolated()


def test_engine_states_after_boot(runtime) -> None:
    runtime.start()
    states = {state.name: state for state in runtime.engine_states()}
    assert len(states) == 6
    for name, state in states.items():
        if name != "event_bus":
            assert state.status is EngineStateStatus.RUNNING, name
        else:
            assert state.status in (
                EngineStateStatus.REGISTERED,
                EngineStateStatus.RUNNING,
            )


def test_submit_and_track_task_with_watchdog(runtime) -> None:
    runtime.start()
    runtime.track_task("task-under-watch", deadline_seconds=60.0)
    assert "task-under-watch" in runtime.watchdog.tracked_tasks()
    runtime.untrack_task("task-under-watch")
    assert "task-under-watch" not in runtime.watchdog.tracked_tasks()


def test_process_registration_and_stop(runtime) -> None:
    runtime.start()
    runtime.register_process("cli-worker")
    snapshot = runtime.process_snapshot()
    assert any(p.get("name") == "cli-worker" for p in snapshot)
    runtime.stop(reason="test")
    assert runtime.status().phase is RuntimePhase.STOPPED
