"""Unit tests for the RuntimeEngine facade (uses the repo runtime config)."""

from __future__ import annotations

import pytest

from ai_company.runtime import RuntimeEngine, create_runtime
from ai_company.runtime.models import (
    EngineNotRegisteredError,
    HealthStatus,
    RuntimePhase,
)


@pytest.fixture
def runtime() -> RuntimeEngine:
    engine = create_runtime(config_dir="config")
    yield engine
    try:
        status = engine.status()
        if status is not None and status.phase.value == "running":
            engine.stop(reason="test-teardown")
    except Exception:
        pass


def test_construction_and_identity(runtime: RuntimeEngine) -> None:
    assert runtime.name == "AI Enterprise Runtime"
    assert runtime.lifecycle.phase is RuntimePhase.STOPPED
    assert runtime.runtime_id.startswith("rt_")


def test_register_and_unregister_engine(runtime: RuntimeEngine) -> None:
    instance = object()
    state = runtime.register_engine("probe", instance)
    assert state.name == "probe"
    assert runtime.get_engine("probe") is instance
    assert runtime.unregister_engine("probe") is True
    with pytest.raises(EngineNotRegisteredError):
        runtime.get_engine("probe")


def test_get_engine_optional_missing(runtime: RuntimeEngine) -> None:
    assert runtime.get_engine_optional("nope") is None


def test_register_handler_dispatches(runtime: RuntimeEngine) -> None:
    received: list[tuple[str, dict]] = []

    def handler(event_type: str, payload: dict) -> None:
        received.append((event_type, payload))

    runtime.register_handler("runtime.job_executed", handler)
    runtime._dispatch_local("runtime.job_executed", {"job": "x"})
    assert received == [("runtime.job_executed", {"job": "x"})]


def test_engine_states_empty_before_start(runtime: RuntimeEngine) -> None:
    assert runtime.engine_states() == []


def test_builtin_job_handlers_registered(runtime: RuntimeEngine) -> None:
    for name in (
        "noop",
        "event_publish",
        "memory_consolidation",
        "orchestrate_pipeline",
    ):
        assert name in runtime._job_handlers


def test_job_noop_and_event_publish(runtime: RuntimeEngine) -> None:
    class _FakeJob:
        name = "test-job"
        params = {"event_type": "runtime.job_executed", "message": "hi"}

    runtime._job_noop(_FakeJob(), runtime)
    runtime._job_event_publish(_FakeJob(), runtime)
    assert runtime.metrics_registry.counter("jobs_executed") == 1


def test_health_on_stopped_runtime(runtime: RuntimeEngine) -> None:
    # Health probes work even before startup (system check at minimum).
    checks = runtime.health()
    assert any(c.component == "system" for c in checks)
    assert all(c.status is HealthStatus.HEALTHY for c in checks)


def test_metrics_on_stopped_runtime(runtime: RuntimeEngine) -> None:
    metrics = runtime.metrics()
    assert metrics.active_engines == 0
    assert metrics.uptime_seconds >= 0
