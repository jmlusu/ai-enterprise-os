"""Unit tests for the pipeline execution runtime."""

from __future__ import annotations

from typing import Any

from ai_company.orchestration.checkpoint import CheckpointManager
from ai_company.orchestration.executor import TaskResult
from ai_company.orchestration.models import (
    ExecutionMetrics,
    OrchestrationPlan,
    Pipeline,
    PipelineStage,
    PipelineStatus,
    PipelineTask,
    StageMode,
    TaskStatus,
)
from ai_company.orchestration.pipeline import PipelineRunner


class StubExecutor:
    """Executor stub that returns configured TaskResults per task."""

    def __init__(self, results: dict[str, TaskResult] | None = None) -> None:
        self.results = results or {}
        self.calls: list[str] = []

    def execute_task(
        self, task: PipelineTask, context: dict[str, Any] | None = None
    ) -> TaskResult:
        self.calls.append(task.id)
        if task.id in self.results:
            return self.results[task.id]
        return TaskResult(
            task_id=task.id,
            status="completed",
            output={"success": True, "task_id": task.id},
        )


def _task(
    task_id: str,
    deps: list[str] | None = None,
    on_failure: str = "fail",
    rollback_action: str | None = None,
) -> PipelineTask:
    return PipelineTask(
        id=task_id,
        name=task_id,
        task_type="noop",
        engine="test",
        dependencies=list(deps or []),
        on_failure=on_failure,
        rollback_action=rollback_action,
    )


def _plan(
    name: str = "p",
    stages: list[PipelineStage] | None = None,
) -> OrchestrationPlan:
    pipeline = Pipeline(
        id=f"pipeline_{name}",
        name=name,
        stages=stages
        or [
            PipelineStage(
                id="s1",
                name="S1",
                mode=StageMode.SEQUENTIAL,
                tasks=[_task("t1"), _task("t2")],
            )
        ],
    )
    return OrchestrationPlan(name=name, pipeline=pipeline)


def _runner(
    executor: StubExecutor,
    checkpoint_manager: Any | None = None,
    checkpoints_config: dict[str, Any] | None = None,
    rollback_manager: Any | None = None,
) -> PipelineRunner:
    return PipelineRunner(
        executor=executor,
        checkpoint_manager=checkpoint_manager,
        checkpoints_config=checkpoints_config or {},
        rollback_manager=rollback_manager,
    )


class TestPipelineRunner:
    def test_sequential_stage_runs_all_tasks(self) -> None:
        executor = StubExecutor()
        plan = _plan()
        result = _runner(executor).run(plan)
        assert result.success is True
        assert executor.calls == ["t1", "t2"]
        assert result.metrics.tasks_completed == 2
        assert result.metrics.tasks_failed == 0

    def test_parallel_stage_runs_all_tasks(self) -> None:
        executor = StubExecutor()
        plan = _plan(
            "parallel",
            stages=[
                PipelineStage(
                    id="s1",
                    name="S1",
                    mode=StageMode.PARALLEL,
                    tasks=[_task("a"), _task("b"), _task("c")],
                )
            ],
        )
        result = _runner(executor).run(plan)
        assert result.success is True
        assert sorted(executor.calls) == ["a", "b", "c"]
        assert result.metrics.tasks_completed == 3

    def test_dependency_order_in_parallel_stage(self) -> None:
        executor = StubExecutor()
        plan = _plan(
            "ordered",
            stages=[
                PipelineStage(
                    id="s1",
                    name="S1",
                    mode=StageMode.PARALLEL,
                    tasks=[
                        _task("c", ["a"]),
                        _task("a"),
                        _task("b", ["a"]),
                    ],
                )
            ],
        )
        result = _runner(executor).run(plan)
        assert result.success is True
        assert executor.calls.index("a") < executor.calls.index("b")
        assert executor.calls.index("a") < executor.calls.index("c")

    def test_failed_task_fails_pipeline(self) -> None:
        executor = StubExecutor(
            {"t2": TaskResult(task_id="t2", status="failed", error="boom")}
        )
        plan = _plan()
        result = _runner(executor).run(plan)
        assert result.status == PipelineStatus.FAILED
        assert result.state.task_errors["t2"] == "boom"
        assert result.metrics.tasks_failed == 1

    def test_on_failure_skip_continues(self) -> None:
        executor = StubExecutor(
            {"t1": TaskResult(task_id="t1", status="failed", error="boom")}
        )
        plan = _plan(
            "skip",
            stages=[
                PipelineStage(
                    id="s1",
                    name="S1",
                    mode=StageMode.SEQUENTIAL,
                    tasks=[
                        _task("t1", on_failure="skip"),
                        _task("t2"),
                    ],
                )
            ],
        )
        result = _runner(executor).run(plan)
        assert result.success is True
        assert result.metrics.tasks_completed == 1
        assert result.metrics.tasks_failed == 1

    def test_conditional_stage_skipped(self) -> None:
        executor = StubExecutor()
        plan = _plan(
            "cond",
            stages=[
                PipelineStage(
                    id="gate",
                    name="Gate",
                    mode=StageMode.CONDITIONAL,
                    condition="enable == true",
                    tasks=[_task("only_if_enabled")],
                ),
                PipelineStage(
                    id="always",
                    name="Always",
                    mode=StageMode.SEQUENTIAL,
                    tasks=[_task("t2")],
                ),
            ],
        )
        result = _runner(executor).run(plan)
        assert result.success is True
        assert executor.calls == ["t2"]
        assert result.metrics.tasks_skipped == 1

    def test_conditional_stage_runs_when_condition_met(self) -> None:
        executor = StubExecutor()
        plan = _plan(
            "cond2",
            stages=[
                PipelineStage(
                    id="gate",
                    name="Gate",
                    mode=StageMode.CONDITIONAL,
                    condition="true",
                    tasks=[_task("t1")],
                )
            ],
        )
        result = _runner(executor).run(plan)
        assert result.success is True
        assert executor.calls == ["t1"]

    def test_rollback_handler_registered_on_completion(self) -> None:
        from ai_company.orchestration.rollback import RollbackManager

        rollback_manager = RollbackManager()
        executor = StubExecutor()
        plan = _plan(
            "rollback",
            stages=[
                PipelineStage(
                    id="s1",
                    name="S1",
                    mode=StageMode.SEQUENTIAL,
                    tasks=[
                        _task("t1", rollback_action="memory.delete"),
                        _task("t2"),
                    ],
                )
            ],
        )
        result = _runner(executor, rollback_manager=rollback_manager).run(plan)
        assert result.success is True
        assert "t1" in rollback_manager.list_handlers()
        assert rollback_manager.has_handlers() is True

    def test_resume_from_checkpoint_skips_completed_tasks(self) -> None:
        executor = StubExecutor()
        plan = _plan(
            "resume",
            stages=[
                PipelineStage(
                    id="s1",
                    name="S1",
                    mode=StageMode.SEQUENTIAL,
                    tasks=[_task("t1"), _task("t2"), _task("t3")],
                )
            ],
        )
        checkpoints_config = {"enabled": True}
        checkpoint_manager = CheckpointManager(config=checkpoints_config)

        # Run once with a checkpoint written after t2.
        runner = _runner(executor, checkpoint_manager, checkpoints_config)
        result = runner.run(plan)
        assert result.success is True

        checkpoint = checkpoint_manager.latest(plan.pipeline.id)
        assert checkpoint is not None
        # Completed tasks must be present in the checkpoint state.
        assert checkpoint.state.task_statuses["t1"] == TaskStatus.COMPLETED

        # A fresh executor run resuming from the checkpoint must not re-run t1/t2.
        executor2 = StubExecutor()
        result2 = _runner(executor2, checkpoint_manager, checkpoints_config).run(
            plan, checkpoint=checkpoint
        )
        assert result2.success is True
        assert set(executor2.calls) <= {"t3"}

    def test_checkpoint_written_after_tasks(self) -> None:
        executor = StubExecutor()
        plan = _plan()
        checkpoint_manager = CheckpointManager(
            config={"enabled": True, "max_checkpoints_per_pipeline": 10}
        )
        result = _runner(
            executor, checkpoint_manager, {"auto_checkpoint_on_task_completed": True}
        ).run(plan)
        assert result.success is True
        assert len(checkpoint_manager.all()) >= 2

    def test_pipeline_status_transitions(self) -> None:
        executor = StubExecutor()
        result = _runner(executor).run(_plan())
        assert result.state.status == PipelineStatus.COMPLETED
        assert result.state.started_at is not None
        assert result.state.completed_at is not None

    def test_execution_metrics_recorded(self) -> None:
        executor = StubExecutor()
        metrics: ExecutionMetrics = _runner(executor).run(_plan()).metrics
        assert metrics.tasks_total == 2
        assert metrics.tasks_completed == 2
        assert metrics.duration_seconds >= 0
        assert metrics.completed_at is not None
