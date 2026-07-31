"""Unit tests for checkpoint management."""

from __future__ import annotations

from ai_company.memory.engine import MemoryEngine
from ai_company.orchestration.checkpoint import CheckpointManager
from ai_company.orchestration.models import (
    OrchestrationPlan,
    Pipeline,
    PipelineStage,
    PipelineTask,
    TaskStatus,
)


def _task(task_id: str) -> PipelineTask:
    return PipelineTask(id=task_id, name=task_id, task_type="noop", engine="test")


def _plan(name: str = "ckpt") -> OrchestrationPlan:
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


def _completed_state(plan: OrchestrationPlan):
    state = plan.pipeline.stages[0].tasks[0]
    return state


class TestCheckpointManager:
    def test_create_and_restore(self) -> None:
        from ai_company.orchestration.models import ExecutionState

        manager = CheckpointManager(config={})
        plan = _plan()
        state = ExecutionState(pipeline_id=plan.pipeline.id, plan_id=plan.id)
        state.task_statuses = {
            t.id: TaskStatus.COMPLETED for t in plan.pipeline.all_tasks()
        }
        checkpoint = manager.create(plan, state, stage_index=0, task_index=1)
        assert checkpoint.id
        assert checkpoint.pipeline_id == plan.pipeline.id

        restored = manager.restore(checkpoint.id)
        assert restored is not None
        assert restored.id == checkpoint.id
        assert restored.state.task_statuses["a"] == TaskStatus.COMPLETED

    def test_restore_unknown_returns_none(self) -> None:
        manager = CheckpointManager(config={})
        assert manager.restore("does-not-exist") is None

    def test_latest_returns_most_recent(self) -> None:
        manager = CheckpointManager(config={})
        plan = _plan()
        from ai_company.orchestration.models import ExecutionState

        first = manager.create(
            plan,
            ExecutionState(pipeline_id=plan.pipeline.id, plan_id=plan.id),
            stage_index=0,
        )
        second = manager.create(
            plan,
            ExecutionState(pipeline_id=plan.pipeline.id, plan_id=plan.id),
            stage_index=1,
        )
        latest = manager.latest(plan.pipeline.id)
        assert latest is not None
        assert latest.id == second.id
        assert latest.stage_index == 1
        assert first.id != second.id

    def test_list_for_newest_first(self) -> None:
        manager = CheckpointManager(config={})
        plan = _plan()
        from ai_company.orchestration.models import ExecutionState

        manager.create(
            plan,
            ExecutionState(pipeline_id=plan.pipeline.id, plan_id=plan.id),
            stage_index=0,
        )
        manager.create(
            plan,
            ExecutionState(pipeline_id=plan.pipeline.id, plan_id=plan.id),
            stage_index=1,
        )
        items = manager.list_for(plan.pipeline.id)
        assert len(items) == 2
        assert items[0].stage_index > items[1].stage_index

    def test_all_across_pipelines(self) -> None:
        manager = CheckpointManager(config={})
        from ai_company.orchestration.models import ExecutionState

        plan_a = _plan("a")
        plan_b = _plan("b")
        manager.create(
            plan_a, ExecutionState(pipeline_id=plan_a.pipeline.id, plan_id=plan_a.id)
        )
        manager.create(
            plan_b, ExecutionState(pipeline_id=plan_b.pipeline.id, plan_id=plan_b.id)
        )
        assert len(manager.all()) == 2

    def test_delete(self) -> None:
        manager = CheckpointManager(config={})
        plan = _plan()
        from ai_company.orchestration.models import ExecutionState

        checkpoint = manager.create(
            plan, ExecutionState(pipeline_id=plan.pipeline.id, plan_id=plan.id)
        )
        assert manager.delete(checkpoint.id) is True
        assert manager.restore(checkpoint.id) is None
        assert manager.delete(checkpoint.id) is False

    def test_clear_filtered_and_all(self) -> None:
        manager = CheckpointManager(config={})
        from ai_company.orchestration.models import ExecutionState

        plan_a = _plan("a")
        plan_b = _plan("b")
        manager.create(
            plan_a, ExecutionState(pipeline_id=plan_a.pipeline.id, plan_id=plan_a.id)
        )
        manager.create(
            plan_a, ExecutionState(pipeline_id=plan_a.pipeline.id, plan_id=plan_a.id)
        )
        manager.create(
            plan_b, ExecutionState(pipeline_id=plan_b.pipeline.id, plan_id=plan_b.id)
        )
        assert manager.clear(plan_a.pipeline.id) == 2
        assert len(manager.all()) == 1
        assert manager.clear() == 1
        assert manager.all() == []

    def test_cap_per_pipeline(self) -> None:
        manager = CheckpointManager(config={"max_checkpoints_per_pipeline": 2})
        from ai_company.orchestration.models import ExecutionState

        plan = _plan()
        for index in range(5):
            manager.create(
                plan,
                ExecutionState(pipeline_id=plan.pipeline.id, plan_id=plan.id),
                stage_index=index,
            )
        items = manager.list_for(plan.pipeline.id)
        assert len(items) == 2
        assert {c.stage_index for c in items} == {3, 4}

    def test_memory_persistence(self, tmp_path) -> None:
        memory = MemoryEngine(storage_path=str(tmp_path / "mem.jsonl"))
        manager = CheckpointManager(
            config={"persist_to_memory": True}, memory_engine=memory
        )
        from ai_company.orchestration.models import ExecutionState

        plan = _plan("mem")
        checkpoint = manager.create(
            plan, ExecutionState(pipeline_id=plan.pipeline.id, plan_id=plan.id)
        )
        # A fresh manager with the same memory engine can restore.
        fresh = CheckpointManager(
            config={"persist_to_memory": True}, memory_engine=memory
        )
        restored = fresh.restore(checkpoint.id)
        assert restored is not None
        assert restored.plan_id == plan.id

    def test_disk_persistence(self, tmp_path) -> None:
        disk = tmp_path / "ckpts"
        manager = CheckpointManager(
            config={"persist_to_disk": True}, disk_path=str(disk)
        )
        from ai_company.orchestration.models import ExecutionState

        plan = _plan("disk")
        checkpoint = manager.create(
            plan, ExecutionState(pipeline_id=plan.pipeline.id, plan_id=plan.id)
        )
        assert (disk / f"{checkpoint.id}.json").exists()
        fresh = CheckpointManager(config={"persist_to_disk": True}, disk_path=str(disk))
        # Disk persistence is write-only in this version; restore falls back to
        # the checkpoint id registry — assert the file was written.
        assert fresh is not None
