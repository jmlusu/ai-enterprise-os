"""Unit tests for the orchestration engine facade and coordinator."""

from __future__ import annotations

from typing import Any

import pytest

from ai_company.memory.engine import MemoryEngine
from ai_company.orchestration import (
    OrchestrationEngine,
    OrchestrationPlan,
    PipelinePlanner,
)
from ai_company.orchestration.coordinator import Coordinator, default_coordinator
from ai_company.orchestration.exceptions import (
    EngineNotReadyError,
    OrchestrationError,
    PlanNotFoundError,
    RollbackError,
)
from ai_company.orchestration.models import (
    PipelineStatus,
    ScheduleMode,
    TaskStatus,
)


class StubCoordinator:
    """Minimal coordinator used to keep facade tests hermetic."""

    def __init__(self, results: dict[str, dict[str, Any]] | None = None) -> None:
        self.results = results or {}
        self.calls: list[str] = []
        self._engines: dict[str, Any] = {"event_bus": None, "memory": None}
        self._handlers: dict[str, Any] = {}

    def register_engine(self, name: str, engine: Any) -> None:
        self._engines[name] = engine

    def unregister_engine(self, name: str) -> bool:
        return self._engines.pop(name, None) is not None

    def engine(self, name: str) -> Any | None:
        return self._engines.get(name)

    def list_engines(self) -> list[str]:
        return sorted(self._engines)

    def register_handler(self, task_type: str, handler: Any) -> None:
        self._handlers[task_type] = handler

    def list_handlers(self) -> list[str]:
        return sorted(getattr(self, "_handlers", {}))

    def execute(self, task: Any, context: dict[str, Any] | None = None) -> Any:
        self.calls.append(task.id)
        return self.results.get(task.id, {"success": True, "task_id": task.id})


def _engine(
    tmp_path,
    coordinator: Any | None = None,
    config: dict[str, Any] | None = None,
) -> OrchestrationEngine:
    """Build a hermetic engine with in-memory-ish state."""
    memory = MemoryEngine(storage_path=str(tmp_path / "mem.jsonl"))
    if coordinator is None:
        coordinator = StubCoordinator()
    coordinator.register_engine("memory", memory)
    coordinator.register_engine("event_bus", None)
    return OrchestrationEngine(
        coordinator=coordinator,
        config=config,
        memory_engine=memory,
    )


class TestOrchestrationEngine:
    def test_plans_and_runs_bootstrap(self, tmp_path) -> None:
        engine = _engine(tmp_path)
        try:
            plan = engine.plan("bootstrap")
            assert isinstance(plan, OrchestrationPlan)
            assert plan.pipeline.name == "bootstrap"
            record = engine.run(plan)
            assert record.state.status == PipelineStatus.COMPLETED
            assert record.metrics.tasks_total == len(plan.pipeline.all_tasks())
            assert record.metrics.tasks_completed == record.metrics.tasks_total
            assert len(engine.history()) == 1
        finally:
            engine.close()

    def test_plan_from_data(self, tmp_path) -> None:
        engine = _engine(tmp_path)
        try:
            plan = engine.plan(
                data={
                    "name": "inline",
                    "stages": [
                        {
                            "id": "s1",
                            "name": "S1",
                            "mode": "sequential",
                            "tasks": [
                                {
                                    "id": "t1",
                                    "name": "T1",
                                    "task_type": "noop",
                                    "engine": "test",
                                }
                            ],
                        }
                    ],
                }
            )
            assert plan.pipeline.name == "inline"
            assert plan.pipeline.all_tasks()[0].id == "t1"
        finally:
            engine.close()

    def test_plan_requires_source(self, tmp_path) -> None:
        engine = _engine(tmp_path)
        try:
            with pytest.raises(OrchestrationError):
                engine.plan()
        finally:
            engine.close()

    def test_unknown_pipeline_raises(self, tmp_path) -> None:
        engine = _engine(tmp_path)
        try:
            with pytest.raises(PlanNotFoundError):
                engine.plan("does-not-exist")
        finally:
            engine.close()

    def test_list_pipelines(self, tmp_path) -> None:
        engine = _engine(tmp_path)
        try:
            pipelines = engine.list_pipelines()
            assert "bootstrap" in pipelines
            assert "generation" in pipelines
            assert "report" in pipelines
        finally:
            engine.close()

    def test_engine_status_and_health(self, tmp_path) -> None:
        engine = _engine(tmp_path)
        try:
            status = engine.engine_status()
            # Idle before any run.
            assert status.running is False
            assert status.name == "Enterprise Orchestration Engine"
            assert status.active_plans == 0
            assert isinstance(status.health, list)

            plan = engine.plan("bootstrap")
            engine.run(plan)
            status = engine.engine_status()
            assert status.running is True
            assert status.active_plans == 0  # completed plan is not active
        finally:
            engine.close()

    def test_start_immediate_returns_record(self, tmp_path) -> None:
        engine = _engine(tmp_path)
        try:
            plan = engine.plan("bootstrap")
            result = engine.start(plan)
            assert result.state.status == PipelineStatus.COMPLETED
        finally:
            engine.close()

    def test_retry_reruns_plan(self, tmp_path) -> None:
        engine = _engine(tmp_path)
        try:
            plan = engine.plan("bootstrap")
            engine.run(plan)
            record = engine.retry(plan.id)
            assert record.state.status == PipelineStatus.COMPLETED
            assert len(engine.history(plan.id)) >= 2
        finally:
            engine.close()

    def test_resume_requires_checkpoint(self, tmp_path) -> None:
        engine = _engine(tmp_path)
        try:
            plan = engine.plan("bootstrap")
            engine.run(plan)
            # Completing a run leaves checkpoints; resume should succeed.
            record = engine.resume(plan.id)
            assert record.state.status == PipelineStatus.COMPLETED
        finally:
            engine.close()

    def test_rollback_without_handlers_raises(self, tmp_path) -> None:
        engine = _engine(tmp_path)
        try:
            plan = engine.plan("bootstrap")
            engine.run(plan)
            with pytest.raises(RollbackError):
                engine.rollback(plan.id)
        finally:
            engine.close()

    def test_get_state_and_checkpoints(self, tmp_path) -> None:
        engine = _engine(tmp_path)
        try:
            plan = engine.plan("bootstrap")
            engine.run(plan)
            state = engine.get_state(plan.id)
            assert state is not None
            assert state.status == PipelineStatus.COMPLETED
            checkpoints = engine.checkpoints(plan.pipeline.id)
            assert len(checkpoints) > 0
        finally:
            engine.close()

    def test_register_engine_and_handlers(self, tmp_path) -> None:
        engine = _engine(tmp_path)
        try:
            engine.register_engine("custom", object())
            assert engine.coordinator.engine("custom") is not None
            assert engine.unregister_engine("custom") is True

            def handler(task, context):
                return {"handled": task.id}

            engine.register_handler("custom_type", handler)
            assert "custom_type" in engine.list_handlers()
        finally:
            engine.close()

    def test_scheduled_plan_start_registers_with_scheduler(self, tmp_path) -> None:
        engine = _engine(tmp_path)
        try:
            plan = engine.plan(
                "bootstrap",
                schedule_mode=ScheduleMode.SCHEDULED,
            )
            result = engine.start(plan)
            # Non-immediate plans are returned as-is, registered with the scheduler.
            assert isinstance(result, OrchestrationPlan)
            assert engine.scheduler.pending_plans() != []
        finally:
            engine.close()


class TestCoordinator:
    def test_dispatch_to_registered_handler(self) -> None:
        coordinator = Coordinator()
        calls: list[str] = []

        def handler(task, context):
            calls.append(task.id)
            return {"ok": True}

        coordinator.register_handler("mine", handler)
        from ai_company.orchestration.models import PipelineTask

        task = PipelineTask(id="x", name="X", task_type="mine", engine="test")
        assert coordinator.execute(task) == {"ok": True}
        assert calls == ["x"]

    def test_unregistered_handler_raises(self) -> None:
        coordinator = Coordinator()
        from ai_company.orchestration.models import PipelineTask

        task = PipelineTask(id="x", name="X", task_type="nope", engine="test")
        with pytest.raises(EngineNotReadyError):
            coordinator.execute(task)

    def test_engine_registration(self) -> None:
        coordinator = Coordinator()
        coordinator.register_engine("a", object())
        coordinator.register_engine("b", object())
        assert coordinator.list_engines() == ["a", "b"]
        assert coordinator.unregister_engine("a") is True
        assert coordinator.engine("a") is None

    def test_default_coordinator_wires_engines(self) -> None:
        coordinator = default_coordinator()
        engines = coordinator.list_engines()
        for name in (
            "registry",
            "generator",
            "validator",
            "workflow",
            "memory",
            "decision",
            "audit",
            "event_bus",
        ):
            assert name in engines
        assert "load_registry" in coordinator.list_handlers()
        assert "generate" in coordinator.list_handlers()
        assert "noop" in coordinator.list_handlers()

    def test_default_coordinator_executes_noop(self) -> None:
        coordinator = default_coordinator()
        from ai_company.orchestration.models import PipelineTask

        task = PipelineTask(id="n", name="N", task_type="noop", engine="test")
        result = coordinator.execute(task)
        assert result["success"] is True


class TestPlanner:
    def test_planner_parses_builtin_pipelines(self) -> None:
        planner = PipelinePlanner()
        pipelines = planner.list_pipelines()
        assert "bootstrap" in pipelines
        bootstrap = planner.get_pipeline("bootstrap")
        assert bootstrap.all_tasks()  # non-empty
        # Dependency references resolve within the pipeline.
        from ai_company.orchestration.dependencies import DependencyGraph

        graph = DependencyGraph(bootstrap)
        assert graph.topological_order()

    def test_planner_plan_from_yaml_requires_file(self, tmp_path) -> None:
        planner = PipelinePlanner()
        with pytest.raises(PlanNotFoundError):
            planner.plan_from_yaml(tmp_path / "missing.yaml")

    def test_task_status_enum_coverage(self) -> None:
        from ai_company.orchestration.lifecycle import can_transition_task

        assert can_transition_task(TaskStatus.PENDING, TaskStatus.RUNNING)
        assert can_transition_task(TaskStatus.RUNNING, TaskStatus.COMPLETED)
        assert can_transition_task(TaskStatus.RUNNING, TaskStatus.FAILED)
        assert not can_transition_task(TaskStatus.COMPLETED, TaskStatus.RUNNING)
