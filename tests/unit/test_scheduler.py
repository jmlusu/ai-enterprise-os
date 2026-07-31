"""Unit tests for the orchestration scheduler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ai_company.orchestration.models import (
    OrchestrationPlan,
    Pipeline,
    PipelineStage,
    PipelineTask,
    ScheduleMode,
)
from ai_company.orchestration.scheduler import OrchestrationScheduler

_NOW = datetime.now(UTC)


def _task(task_id: str) -> PipelineTask:
    return PipelineTask(id=task_id, name=task_id, task_type="noop", engine="test")


def _plan(
    name: str,
    mode: ScheduleMode = ScheduleMode.IMMEDIATE,
    scheduled_at: datetime | None = None,
    interval_seconds: float | None = None,
    max_runs: int = 0,
    depends_on: list[str] | None = None,
) -> OrchestrationPlan:
    return OrchestrationPlan(
        name=name,
        pipeline=Pipeline(
            id=f"pipeline_{name}",
            name=name,
            stages=[PipelineStage(id="s1", name="S1", tasks=[_task(f"{name}_t1")])],
        ),
        schedule_mode=mode,
        scheduled_at=scheduled_at,
        interval_seconds=interval_seconds,
        max_runs=max_runs,
        depends_on=list(depends_on or []),
    )


class TestOrchestrationScheduler:
    def test_immediate_due_once(self) -> None:
        scheduler = OrchestrationScheduler()
        plan = _plan("immediate")
        scheduler.register(plan)
        assert scheduler.due_plans() == [plan]
        scheduler.mark_run(plan)
        assert scheduler.due_plans() == []
        # Immediate plans only run once.
        assert scheduler.due_plans(now=_NOW + timedelta(hours=1)) == []

    def test_scheduled_due_after_trigger(self) -> None:
        scheduler = OrchestrationScheduler()
        future = _NOW + timedelta(minutes=5)
        plan = _plan("scheduled", mode=ScheduleMode.SCHEDULED, scheduled_at=future)
        scheduler.register(plan)
        assert scheduler.due_plans(now=_NOW) == []
        assert scheduler.due_plans(now=future) == [plan]
        scheduler.mark_run(plan, now=future)
        assert scheduler.due_plans(now=future + timedelta(hours=1)) == []

    def test_recurring_due_per_interval(self) -> None:
        scheduler = OrchestrationScheduler()
        plan = _plan(
            "recurring",
            mode=ScheduleMode.RECURRING,
            interval_seconds=60.0,
            max_runs=3,
        )
        scheduler.register(plan)
        now = _NOW
        assert scheduler.due_plans(now=now) == [plan]  # first run
        scheduler.mark_run(plan, now=now)
        assert scheduler.due_plans(now=now) == []
        assert scheduler.due_plans(now=now + timedelta(seconds=59)) == []
        assert scheduler.due_plans(now=now + timedelta(seconds=61)) == [plan]
        scheduler.mark_run(plan, now=now + timedelta(seconds=61))
        scheduler.mark_run(plan, now=now + timedelta(seconds=121))
        # max_runs reached -> never due again
        assert scheduler.due_plans(now=now + timedelta(hours=1)) == []

    def test_dependency_waits_for_upstream(self) -> None:
        scheduler = OrchestrationScheduler()
        upstream = _plan("upstream")
        downstream = _plan(
            "downstream", mode=ScheduleMode.DEPENDENCY, depends_on=["upstream"]
        )
        scheduler.register(upstream)
        scheduler.register(downstream)
        assert scheduler.due_plans() == [upstream]
        scheduler.mark_run(upstream)
        scheduler.notify_completed("upstream")
        assert scheduler.due_plans() == [downstream]

    def test_dependency_without_upstream_runs_once(self) -> None:
        scheduler = OrchestrationScheduler()
        plan = _plan("standalone", mode=ScheduleMode.DEPENDENCY)
        scheduler.register(plan)
        assert scheduler.due_plans() == [plan]
        scheduler.mark_run(plan)
        assert scheduler.due_plans() == []

    def test_mark_run_increments_run_count(self) -> None:
        scheduler = OrchestrationScheduler()
        plan = _plan("counted")
        scheduler.register(plan)
        scheduler.mark_run(plan)
        assert plan.run_count == 1

    def test_pending_plans(self) -> None:
        scheduler = OrchestrationScheduler()
        plan = _plan("pending")
        scheduler.register(plan)
        assert plan in scheduler.pending_plans()
        scheduler.mark_run(plan)
        assert plan not in scheduler.pending_plans()

    def test_unregister_removes_plan(self) -> None:
        scheduler = OrchestrationScheduler()
        plan = _plan("removed")
        scheduler.register(plan)
        scheduler.mark_run(plan)
        assert scheduler.unregister(plan.id) is True
        assert scheduler.pending_plans() == []
        assert scheduler.due_plans() == []

    def test_run_once_invokes_callback(self) -> None:
        scheduler = OrchestrationScheduler()
        plan = _plan("cb")
        scheduler.register(plan)
        executed: list[str] = []
        scheduler.on_due = lambda p: executed.append(p.id)
        due = scheduler.run_once()
        assert due == [plan]
        assert executed == [plan.id]
        # The callback consumer is responsible for marking the plan run.
        assert scheduler.due_plans() == [plan]
        scheduler.mark_run(plan)
        assert scheduler.due_plans() == []

    def test_start_stop_worker(self) -> None:
        scheduler = OrchestrationScheduler(settings={"worker_interval_seconds": 0.01})
        scheduler.start()
        assert scheduler._thread is not None and scheduler._thread.is_alive()
        scheduler.stop()
        assert scheduler._thread is None
        # stop is idempotent
        scheduler.stop()

    def test_is_completed(self) -> None:
        scheduler = OrchestrationScheduler()
        assert scheduler.is_completed("x") is False
        scheduler.notify_completed("x")
        assert scheduler.is_completed("x") is True
