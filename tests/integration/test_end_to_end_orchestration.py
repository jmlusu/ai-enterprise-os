"""End-to-end orchestration integration tests.

Exercises the full engine lifecycle: planning, immediate and scheduled
execution, event delivery, recovery, retry, rollback registration, and
the CLI-facing status/history surface.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ai_company.events.models import Event, EventType
from ai_company.orchestration import OrchestrationEngine
from ai_company.orchestration.models import (
    OrchestrationPlan,
    PipelineStatus,
    ScheduleMode,
    TaskStatus,
)


class TestEndToEndOrchestration:
    def test_full_lifecycle(self, orchestration: OrchestrationEngine) -> None:
        plan = orchestration.plan("bootstrap", description="e2e lifecycle")
        record = orchestration.start(plan)
        assert record.state.status == PipelineStatus.COMPLETED

        # Status surface
        status = orchestration.status(plan.id)
        # `running` latches True once the engine has executed a plan.
        assert status.running is True
        assert "completed" in status.message

        # Retry produces a second history record.
        retried = orchestration.retry(plan.id)
        assert retried.state.status == PipelineStatus.COMPLETED
        assert len(orchestration.history(plan.id)) >= 2

        # Engine status + health
        engine_status = orchestration.engine_status()
        assert engine_status.name == "Enterprise Orchestration Engine"
        assert isinstance(engine_status.health, list)

    def test_scheduled_plan_runs_via_scheduler(
        self, orchestration: OrchestrationEngine
    ) -> None:
        future = datetime.now(UTC) + timedelta(seconds=1)
        plan = orchestration.plan(
            "bootstrap",
            schedule_mode=ScheduleMode.SCHEDULED,
            scheduled_at=future,
        )
        started = orchestration.start(plan)
        # Non-immediate: returned as the plan, registered with the scheduler.
        assert isinstance(started, OrchestrationPlan)

        executed: list[OrchestrationPlan] = []
        orchestration.scheduler.on_due = lambda p: executed.append(p)
        orchestration.scheduler.run_once(now=future)
        assert len(executed) == 1

    def test_recurring_plan_due_repeatedly(
        self, orchestration: OrchestrationEngine
    ) -> None:
        plan = orchestration.plan(
            "bootstrap",
            schedule_mode=ScheduleMode.RECURRING,
            interval_seconds=60.0,
            max_runs=2,
        )
        orchestration.scheduler.register(plan)
        now = datetime.now(UTC)
        due1 = orchestration.scheduler.due_plans(now=now)
        assert plan in due1
        orchestration.scheduler.mark_run(plan, now=now)
        assert plan not in orchestration.scheduler.due_plans(now=now)
        assert plan in orchestration.scheduler.due_plans(
            now=now + timedelta(seconds=61)
        )
        orchestration.scheduler.mark_run(plan, now=now + timedelta(seconds=61))
        assert plan not in orchestration.scheduler.due_plans(
            now=now + timedelta(hours=2)
        )

    def test_dependency_plan_waits_for_upstream(
        self, orchestration: OrchestrationEngine
    ) -> None:
        upstream = orchestration.plan("bootstrap")
        downstream = orchestration.plan(
            "bootstrap",
            schedule_mode=ScheduleMode.DEPENDENCY,
            depends_on=[upstream.id],
        )
        orchestration.scheduler.register(upstream)
        orchestration.scheduler.register(downstream)
        assert upstream in orchestration.scheduler.due_plans()
        assert downstream not in orchestration.scheduler.due_plans()

        orchestration.run(upstream)
        orchestration.scheduler.notify_completed(upstream.id)
        assert downstream in orchestration.scheduler.due_plans()

    def test_pipeline_events_published(
        self,
        orchestration: OrchestrationEngine,
        collected_events: list[Event],
    ) -> None:
        plan = orchestration.plan("bootstrap")
        orchestration.run(plan)

        event_types = [e.metadata.event_type for e in collected_events]
        assert EventType("pipeline.started") in event_types
        assert EventType("pipeline.completed") in event_types
        assert EventType("task.started") in event_types
        assert EventType("task.completed") in event_types
        # Pipeline events carry the plan id in their payload.
        pipeline_events = [
            e
            for e in collected_events
            if e.metadata.event_type == EventType("pipeline.started")
        ]
        assert any(e.payload.get("plan_id") == plan.id for e in pipeline_events)

    def test_manual_recovery_with_checkpoint(
        self, orchestration: OrchestrationEngine
    ) -> None:
        plan = orchestration.plan("bootstrap")
        first = orchestration.run(plan)
        assert first.state.status == PipelineStatus.COMPLETED

        # Simulate a failed state, then recover via checkpoint + resume.
        from ai_company.orchestration.models import ExecutionState

        failed_state = ExecutionState(
            pipeline_id=plan.pipeline.id,
            plan_id=plan.id,
            status=PipelineStatus.FAILED,
            error="simulated failure",
        )
        result, checkpoint = orchestration.recovery.recover(
            plan, failed_state, "simulated failure", undo_func=orchestration._undo
        )
        assert result.success is True
        assert checkpoint is not None
        assert checkpoint.pipeline_id == plan.pipeline.id

        resumed = orchestration.run(plan, checkpoint=checkpoint)
        assert resumed.state.status == PipelineStatus.COMPLETED

    def test_task_statuses_populated(self, orchestration: OrchestrationEngine) -> None:
        plan = orchestration.plan("bootstrap")
        record = orchestration.run(plan)
        for task in plan.pipeline.all_tasks():
            assert record.state.task_statuses[task.id] in (
                TaskStatus.COMPLETED,
                TaskStatus.SKIPPED,
            )

    def test_unknown_plan_status_is_safe(
        self, orchestration: OrchestrationEngine
    ) -> None:
        import pytest

        from ai_company.orchestration.exceptions import PlanNotFoundError

        with pytest.raises(PlanNotFoundError):
            orchestration.status("no-such-plan")
