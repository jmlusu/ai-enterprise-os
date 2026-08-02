"""Unit tests for the RuntimeEngine facade (uses the repo runtime config)."""

from __future__ import annotations

import pytest

from ai_company.runtime import RuntimeEngine, create_runtime
from ai_company.runtime.models import (
    EngineNotRegisteredError,
    EngineStateStatus,
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
        "telemetry_retention",
    ):
        assert name in runtime._job_handlers


def test_job_telemetry_retention_runs_fail_open(
    runtime: RuntimeEngine, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The retention job applies policies and never raises (T2)."""
    monkeypatch.chdir(tmp_path)  # keep any truncation inside the tmp dir

    class _FakeJob:
        name = "telemetry_retention"

    runtime._job_telemetry_retention(_FakeJob(), runtime)  # must not raise
    assert runtime._section("telemetry").get("retention", {})


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


def test_engine_policy_applies_to_registered_engine(runtime: RuntimeEngine) -> None:
    # P0-3: engines must resolve the "engine" category recovery policy even
    # though no exact-name policy exists for "probe".
    runtime.register_engine("probe", object())
    policy = runtime.recovery.policy_for("probe")
    assert policy is not None
    assert policy.name == "engine"
    assert "restart" in policy.actions


def test_engine_failure_recovers_via_factory(runtime: RuntimeEngine) -> None:
    # P0-3: a heartbeat failure must restart the engine through its
    # registered factory instead of being isolated on the first failure.
    class _Restartable:
        def __init__(self) -> None:
            self.restarts = 0

        def restart(self) -> None:
            self.restarts += 1

    instance = _Restartable()
    runtime.register_engine("probe", instance)
    runtime.supervisor.on_failure("probe", "heartbeat_timeout")
    assert instance.restarts == 1
    assert runtime.recovery.attempts("probe") == 1
    assert "probe" not in runtime.supervisor.isolated()
    state = runtime.engine_state("probe")
    assert state is not None
    assert state.status is EngineStateStatus.RUNNING
    assert state.health is HealthStatus.HEALTHY
