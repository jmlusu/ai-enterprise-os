"""Unit tests for the recovery manager."""

from __future__ import annotations

from typing import Any

import pytest

from ai_company.orchestration.checkpoint import CheckpointManager
from ai_company.orchestration.exceptions import RecoveryError
from ai_company.orchestration.models import (
    ExecutionState,
    OrchestrationPlan,
    Pipeline,
    PipelineStage,
    PipelineTask,
    RecoveryAction,
)
from ai_company.orchestration.recovery import RecoveryManager
from ai_company.orchestration.rollback import RollbackManager


def _task(task_id: str) -> PipelineTask:
    return PipelineTask(id=task_id, name=task_id, task_type="noop", engine="test")


def _plan(name: str = "r") -> OrchestrationPlan:
    return OrchestrationPlan(
        name=name,
        pipeline=Pipeline(
            id=f"pipeline_{name}",
            name=name,
            stages=[
                PipelineStage(
                    id="s1",
                    name="S1",
                    tasks=[_task("a"), _task("b")],
                )
            ],
        ),
    )


def _state(plan: OrchestrationPlan) -> ExecutionState:
    return ExecutionState(pipeline_id=plan.pipeline.id, plan_id=plan.id)


class TestRecoveryManager:
    def test_checkpoint_first_strategy(self) -> None:
        plan = _plan()
        checkpoint_manager = CheckpointManager(config={})
        checkpoint_manager.create(plan, _state(plan), stage_index=0)
        recovery = RecoveryManager(
            config={"strategy": "checkpoint_first"},
            checkpoint_manager=checkpoint_manager,
            rollback_manager=RollbackManager(),
        )
        result, resume = recovery.recover(plan, _state(plan), "test failure")
        assert result.success is True
        assert RecoveryAction.CHECKPOINT_RESTORE in result.actions_taken
        assert resume is not None
        assert result.checkpoint_id == resume.id

    def test_rollback_then_retry_strategy(self) -> None:
        plan = _plan()
        rollback_manager = RollbackManager()
        rollback_manager.register_handler("a", "memory.delete", {"id": "1"})
        recovery = RecoveryManager(
            config={"strategy": "rollback_then_retry"},
            rollback_manager=rollback_manager,
        )
        undos: list[tuple[str, str, dict[str, Any]]] = []

        def undo(task_id: str, action: str, params: dict[str, Any]) -> None:
            undos.append((task_id, action, params))

        result, resume = recovery.recover(plan, _state(plan), "boom", undo_func=undo)
        assert result.success is True
        assert result.actions_taken == [RecoveryAction.ROLLBACK, RecoveryAction.RETRY]
        assert result.rolled_back == ["a"]
        assert undos == [("a", "memory.delete", {"id": "1"})]
        assert resume is None

    def test_retry_only_strategy(self) -> None:
        plan = _plan()
        recovery = RecoveryManager(
            config={"strategy": "retry_only"},
        )
        result, resume = recovery.recover(plan, _state(plan), "boom")
        assert result.actions_taken == [RecoveryAction.RETRY]
        assert result.success is True
        assert resume is None

    def test_no_checkpoint_and_no_handlers(self) -> None:
        plan = _plan()
        recovery = RecoveryManager(
            config={"strategy": "checkpoint_first", "retry_failed_tasks": False},
            checkpoint_manager=CheckpointManager(config={}),
            rollback_manager=RollbackManager(),
        )
        result, resume = recovery.recover(plan, _state(plan), "boom")
        assert result.success is False
        assert result.actions_taken == []
        assert resume is None
        assert "No recovery actions" in result.message

    def test_disabled_recovery_raises(self) -> None:
        recovery = RecoveryManager(config={"enabled": False})
        with pytest.raises(RecoveryError, match="disabled"):
            recovery.recover(_plan(), _state(_plan()), "boom")

    def test_should_retry(self) -> None:
        assert (
            RecoveryManager(config={"enabled": True}).should_retry(
                _plan(), _state(_plan())
            )
            is True
        )
        assert (
            RecoveryManager(
                config={"enabled": True, "retry_failed_tasks": False}
            ).should_retry(_plan(), _state(_plan()))
            is False
        )
        assert (
            RecoveryManager(config={"enabled": False}).should_retry(
                _plan(), _state(_plan())
            )
            is False
        )

    def test_should_rollback(self) -> None:
        plan = _plan()
        state = _state(plan)
        empty = RecoveryManager(config={}, rollback_manager=RollbackManager())
        assert empty.should_rollback(plan, state) is False
        rollback_manager = RollbackManager()
        rollback_manager.register_handler("a", "noop")
        with_handlers = RecoveryManager(config={}, rollback_manager=rollback_manager)
        assert with_handlers.should_rollback(plan, state) is True
        disabled = RecoveryManager(
            config={"rollback_on_unrecoverable": False},
            rollback_manager=rollback_manager,
        )
        assert disabled.should_rollback(plan, state) is False

    def test_restore_disabled_skips_checkpoint(self) -> None:
        plan = _plan()
        checkpoint_manager = CheckpointManager(config={})
        checkpoint_manager.create(plan, _state(plan), stage_index=0)
        recovery = RecoveryManager(
            config={
                "strategy": "checkpoint_first",
                "restore_latest_checkpoint": False,
                "retry_failed_tasks": False,
            },
            checkpoint_manager=checkpoint_manager,
        )
        result, resume = recovery.recover(plan, _state(plan), "boom")
        assert resume is None
        assert RecoveryAction.CHECKPOINT_RESTORE not in result.actions_taken
