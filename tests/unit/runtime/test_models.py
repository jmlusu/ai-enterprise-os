"""Unit tests for runtime data models and the event bus adapter."""

from __future__ import annotations

import pytest

from ai_company.runtime.models import (
    RUNTIME_EVENT_MAP,
    EngineState,
    HealthCheck,
    HealthStatus,
    Heartbeat,
    JobKind,
    RecoveryPolicy,
    RuntimeConfig,
    RuntimeTask,
    publish_runtime_event,
)


def test_runtime_config_validation() -> None:
    config = RuntimeConfig()
    assert config.name == "AI Enterprise Runtime"
    assert config.max_workers >= 1
    assert config.loop_interval_seconds > 0
    assert config.persist_state is True


def test_runtime_config_rejects_bad_workers() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RuntimeConfig(max_workers=0)


def test_engine_state_defaults() -> None:
    state = EngineState(name="memory")
    assert state.status.value == "registered"
    assert state.health is HealthStatus.HEALTHY
    assert state.restart_count == 0


def test_health_check_roundtrip() -> None:
    check = HealthCheck(
        name="check_memory",
        component="memory",
        status=HealthStatus.DEGRADED,
        details={"reason": "high load"},
    )
    data = check.model_dump(mode="json")
    restored = HealthCheck.model_validate(data)
    assert restored.component == "memory"
    assert restored.details == {"reason": "high load"}


def test_heartbeat_roundtrip() -> None:
    heartbeat = Heartbeat(component="engine-a", seq=3)
    assert heartbeat.seq == 3
    restored = Heartbeat.from_json(heartbeat.to_json())
    assert restored.component == "engine-a"


def test_runtime_task_defaults() -> None:
    task = RuntimeTask(name="job-1")
    assert task.kind is JobKind.ONE_TIME
    assert task.enabled is True
    assert task.max_runs == 0  # unlimited
    assert task.status.value == "pending"


def test_runtime_task_serializes() -> None:
    task = RuntimeTask(name="job-1", kind="cron", cron="0 7 * * *")
    restored = RuntimeTask.model_validate(task.model_dump(mode="json"))
    assert restored.cron == "0 7 * * *"


def test_recovery_policy_defaults() -> None:
    policy = RecoveryPolicy(name="engine")
    assert policy.actions == ["restart", "reload_state", "isolate"]
    # None means "inherit default_max_attempts from the recovery config"
    assert policy.max_attempts is None


def test_event_map_covers_runtime_contract() -> None:
    expected = {
        "runtime.started",
        "runtime.stopped",
        "runtime.restarted",
        "runtime.reloaded",
        "runtime.degraded",
        "runtime.recovered",
        "runtime.state_recovered",
        "runtime.component_failed",
        "runtime.component_restarted",
        "runtime.heartbeat_missed",
        "runtime.job_executed",
        "runtime.job_failed",
        "runtime.engine_isolated",
        "runtime.engine_unisolated",
    }
    assert expected <= set(RUNTIME_EVENT_MAP)


def test_publish_runtime_event_with_none_bus_is_noop() -> None:
    publish_runtime_event(None, "runtime.started", {})  # must not raise


def test_publish_runtime_event_unknown_type_never_raises() -> None:
    class _FakeBus:
        def publish_event(self, **kwargs) -> None:
            raise RuntimeError("should not be called")

    # Unknown event types are mapped, so the fake bus IS called; wrap to
    # assert the adapter itself never raises for any input.
    publish_runtime_event(_FakeBus(), "totally.unknown", {})
