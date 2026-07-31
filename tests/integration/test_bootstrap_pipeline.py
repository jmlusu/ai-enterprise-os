"""Integration tests: the full bootstrap pipeline through real engines."""

from __future__ import annotations

from ai_company.orchestration import OrchestrationEngine
from ai_company.orchestration.models import PipelineStatus, TaskStatus


class TestBootstrapPipeline:
    def test_bootstrap_pipeline_completes(
        self, orchestration: OrchestrationEngine
    ) -> None:
        plan = orchestration.plan("bootstrap")
        record = orchestration.run(plan)

        assert record.state.status == PipelineStatus.COMPLETED
        assert record.state.error is None
        assert record.metrics.tasks_total == len(plan.pipeline.all_tasks())
        assert record.metrics.tasks_completed == record.metrics.tasks_total
        assert record.metrics.tasks_failed == 0

        # Every task must have a result recorded.
        for task in plan.pipeline.all_tasks():
            assert task.id in record.state.task_results

    def test_bootstrap_registry_loaded(
        self, orchestration: OrchestrationEngine
    ) -> None:
        plan = orchestration.plan("bootstrap")
        record = orchestration.run(plan)
        registry_result = record.state.task_results.get("load_registry")
        assert registry_result is not None
        assert registry_result["success"] is True
        assert registry_result["executives"] > 0
        assert registry_result["departments"] > 0

    def test_bootstrap_persists_memory_and_audit(
        self, orchestration: OrchestrationEngine
    ) -> None:
        plan = orchestration.plan("bootstrap")
        record = orchestration.run(plan)
        assert record.state.status == PipelineStatus.COMPLETED

        memory = orchestration.coordinator.engine("memory")
        assert memory is not None
        # The bootstrap pipeline's memory_save task uses the coordinator
        # default namespace ("global") since no namespace param is declared.
        entries = memory.search(namespace="global", limit=50)
        assert len(entries) >= 1

        audit = orchestration.coordinator.engine("audit")
        assert audit is not None
        events = audit.get_events(limit=50)
        assert len(events) >= 1

    def test_bootstrap_checkpoints_written(
        self, orchestration: OrchestrationEngine
    ) -> None:
        plan = orchestration.plan("bootstrap")
        orchestration.run(plan)
        checkpoints = orchestration.checkpoints(plan.pipeline.id)
        assert len(checkpoints) > 0
        latest = orchestration.checkpoint_manager.latest(plan.pipeline.id)
        assert latest is not None
        # Checkpoints snapshot in-flight state at stage boundaries, so the
        # latest one may capture the run before the final COMPLETED transition.
        assert latest.state.status in (
            PipelineStatus.RUNNING,
            PipelineStatus.COMPLETED,
        )

    def test_bootstrap_resume_from_checkpoint(
        self, orchestration: OrchestrationEngine
    ) -> None:
        plan = orchestration.plan("bootstrap")
        first = orchestration.run(plan)
        assert first.state.status == PipelineStatus.COMPLETED

        # Resume from the latest checkpoint: completed tasks are preserved.
        resumed = orchestration.resume(plan.id)
        assert resumed.state.status == PipelineStatus.COMPLETED
        for task in plan.pipeline.all_tasks():
            assert resumed.state.task_statuses[task.id] == TaskStatus.COMPLETED

    def test_bootstrap_history_recorded(
        self, orchestration: OrchestrationEngine
    ) -> None:
        plan = orchestration.plan("bootstrap")
        orchestration.run(plan)
        history = orchestration.history(plan.id)
        assert len(history) == 1
        assert history[0].plan_id == plan.id
        assert history[0].state.status == PipelineStatus.COMPLETED
        assert history[0].metrics.tasks_completed == history[0].metrics.tasks_total
