"""Unit tests for the runtime recovery manager."""

from __future__ import annotations

from ai_company.runtime.models import RecoveryPolicy
from ai_company.runtime.recovery import RecoveryManager


def test_no_policy_returns_failure() -> None:
    manager = RecoveryManager(config={})
    result = manager.recover("engine-a", reason="test")
    assert result.success is False
    assert "No enabled recovery policy" in result.message


def test_exact_match_policy_wins() -> None:
    manager = RecoveryManager(
        config={
            "policies": {
                "engine-a": {"actions": ["restart"], "max_attempts": 2},
                "engine-*": {"actions": ["isolate"], "max_attempts": 2},
            }
        }
    )
    assert manager.policy_for("engine-a").name == "engine-a"
    assert manager.policy_for("engine-b").name == "engine-*"


def test_category_fallback_engine_policy() -> None:
    manager = RecoveryManager(
        config={"policies": {"engine": {"actions": ["restart"], "max_attempts": 3}}},
        is_engine=lambda name: name == "memory",
    )
    policy = manager.policy_for("memory")
    assert policy is not None
    assert policy.name == "engine"
    assert "restart" in policy.actions
    # Unknown components without a category still get no policy.
    assert manager.policy_for("unknown") is None


def test_category_fallback_process_policy() -> None:
    from ai_company.runtime.process_manager import ProcessManager

    process_manager = ProcessManager()
    process_manager.register("worker-1")
    manager = RecoveryManager(
        config={"policies": {"process": {"actions": ["restart", "isolate"]}}},
        process_manager=process_manager,
    )
    assert manager.policy_for("worker-1").name == "process"


def test_isolate_without_process_fails_honestly() -> None:
    manager = RecoveryManager(
        config={"policies": {"engine-a": {"actions": ["isolate"]}}}
    )
    result = manager.recover("engine-a")
    assert result.success is False
    assert "All recovery actions failed" in result.message


def test_restart_via_factory() -> None:
    calls: list[str] = []

    def factory() -> None:
        calls.append("recreated")

    manager = RecoveryManager(
        config={"policies": {"engine-a": {"actions": ["restart"]}}}
    )
    manager.register_factory("engine-a", factory)
    result = manager.recover("engine-a", reason="test")
    assert result.success is True
    assert result.actions_taken == ["restart"]
    assert calls == ["recreated"]


def test_max_attempts_exhausted() -> None:
    manager = RecoveryManager(
        config={
            "default_max_attempts": 1,
            "policies": {"engine-a": {"actions": ["restart"]}},
        }
    )
    first = manager.recover("engine-a", reason="test")
    assert first.success is False  # no restart mechanism
    second = manager.recover("engine-a", reason="test")
    assert second.success is False
    assert "Max attempts" in second.message
    assert manager.attempts("engine-a") == 2


def test_reset_attempts() -> None:
    manager = RecoveryManager(
        config={"policies": {"engine-a": {"actions": ["restart"]}}}
    )
    manager.recover("engine-a")
    assert manager.attempts("engine-a") == 1
    manager.reset("engine-a")
    assert manager.attempts("engine-a") == 0


def test_disabled_policy_skips() -> None:
    manager = RecoveryManager(
        config={
            "policies": {
                "engine-a": RecoveryPolicy(
                    name="engine-a", actions=["restart"], enabled=False
                )
            }
        }
    )
    result = manager.recover("engine-a")
    assert result.success is False


def test_isolate_action_stops_process() -> None:
    from ai_company.runtime.process_manager import ProcessManager

    manager_process = ProcessManager()
    manager_process.register("engine-a")
    recovery = RecoveryManager(
        config={"policies": {"engine-a": {"actions": ["isolate"]}}},
        process_manager=manager_process,
    )
    result = recovery.recover("engine-a")
    assert result.success is True
    assert result.actions_taken == ["isolate"]


def test_unknown_action_fails_gracefully() -> None:
    manager = RecoveryManager(
        config={"policies": {"engine-a": {"actions": ["teleport"]}}}
    )
    result = manager.recover("engine-a")
    assert result.success is False
    assert "All recovery actions failed" in result.message


def test_results_are_recorded() -> None:
    manager = RecoveryManager(
        config={"policies": {"engine-a": {"actions": ["restart"]}}}
    )
    manager.recover("engine-a")
    manager.recover("engine-a")
    assert len(manager.results("engine-a")) == 2


def test_snapshot() -> None:
    manager = RecoveryManager(
        config={"policies": {"engine-a": {"actions": ["restart"]}}}
    )
    snapshot = manager.snapshot()
    assert snapshot["policies"] == ["engine-a"]
