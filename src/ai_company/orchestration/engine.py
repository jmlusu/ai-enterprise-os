"""Enterprise Orchestration Engine — the COO of AI Enterprise OS.

The engine coordinates the Configuration Registry, Bootstrap, Generator,
Workflow, Decision, Memory, Event Bus, Graph, Reporting, and Audit
engines. It plans declarative pipelines, schedules them, executes tasks
through the coordinator, checkpoints progress, rolls back on failure,
and recovers interrupted runs.

Responsibilities are deliberately separated:

- planning -> :class:`~ai_company.orchestration.planner.PipelinePlanner`
- scheduling -> :class:`~ai_company.orchestration.scheduler.OrchestrationScheduler`
- execution -> :class:`~ai_company.orchestration.pipeline.PipelineRunner`
- task dispatch -> :class:`~ai_company.orchestration.coordinator.Coordinator`
- durability -> state store / checkpoints / rollback / recovery
- observability -> health / metrics / monitoring / notifications
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from ai_company.orchestration.checkpoint import CheckpointManager
from ai_company.orchestration.config import (
    default_retry_policy,
    load_all_orchestration_configs,
)
from ai_company.orchestration.coordinator import Coordinator, default_coordinator
from ai_company.orchestration.exceptions import (
    CheckpointError,
    EngineNotReadyError,
    OrchestrationError,
    PlanNotFoundError,
    RollbackError,
)
from ai_company.orchestration.executor import TaskExecutor
from ai_company.orchestration.health import HealthChecker
from ai_company.orchestration.metrics import MetricsCollector
from ai_company.orchestration.models import (
    Checkpoint,
    EngineStatus,
    ExecutionMetrics,
    ExecutionRecord,
    ExecutionState,
    HealthStatus,
    OrchestrationPlan,
    PipelineStatus,
    RetryPolicy,
    RollbackPlan,
    ScheduleMode,
)
from ai_company.orchestration.monitoring import Monitor
from ai_company.orchestration.notifications import Notifier
from ai_company.orchestration.pipeline import PipelineResult, PipelineRunner
from ai_company.orchestration.planner import PipelinePlanner
from ai_company.orchestration.recovery import RecoveryManager
from ai_company.orchestration.rollback import RollbackManager
from ai_company.orchestration.scheduler import OrchestrationScheduler
from ai_company.orchestration.state import ExecutionStateStore

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class OrchestrationEngine:
    """Facade over the orchestration components.

    Args:
        coordinator: Task coordinator (defaults to real engines).
        config: Full orchestration config dict (defaults to
            ``load_all_orchestration_configs()``).
        event_bus: Override Event Bus used for notifications.
        memory_engine: Override Memory Engine used for state/checkpoints.
        runner: Override the pipeline runner (testing).
        planner: Override the pipeline planner (testing).
    """

    def __init__(
        self,
        coordinator: Coordinator | None = None,
        config: dict[str, Any] | None = None,
        event_bus: Any | None = None,
        memory_engine: Any | None = None,
        runner: PipelineRunner | None = None,
        planner: PipelinePlanner | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.config = config or load_all_orchestration_configs()

        engine_cfg = self.config.get("engine", {}).get("engine", {})
        self.name = str(engine_cfg.get("name", "Enterprise Orchestration Engine"))
        self.version = str(engine_cfg.get("version", "1.0"))
        max_workers = int(engine_cfg.get("max_workers", 4))
        dry_run = bool(engine_cfg.get("dry_run", False))

        dependencies_cfg = self.config.get("dependencies", {}).get("dependencies", {})
        checkpoints_cfg = self.config.get("checkpoints", {}).get("checkpoints", {})
        recovery_cfg = self.config.get("recovery", {}).get("recovery", {})
        monitoring_cfg = self.config.get("monitoring", {}).get("monitoring", {})
        notifications_cfg = self.config.get("notifications", {}).get(
            "notifications", {}
        )
        retries_cfg = self.config.get("retries", {}).get("retries", {})
        scheduler_cfg = self.config.get("scheduler", {}).get("scheduler", {})
        config_pipelines = self.config.get("engine", {}).get("pipelines", {})

        # Coordinator + notification bus
        self.coordinator = coordinator or default_coordinator(
            memory_engine=memory_engine, event_bus=event_bus
        )
        if event_bus is not None:
            self.coordinator.register_engine("event_bus", event_bus)
        bus = self.coordinator.engine("event_bus")

        # Components
        self.notifier = Notifier(notifications_cfg, bus)
        memory = self.coordinator.engine("memory")
        self.state_store = ExecutionStateStore(
            memory_engine=memory,
            namespace=str(
                monitoring_cfg.get(
                    "history_namespace",
                    engine_cfg.get("history_namespace", "orchestration"),
                )
            ),
            persist=bool(engine_cfg.get("persist_history", True)),
            max_records=int(monitoring_cfg.get("history_max_records", 1000)),
        )
        self.checkpoint_manager = CheckpointManager(
            checkpoints_cfg, memory_engine=memory
        )
        self.rollback_manager = RollbackManager()
        retry_policy = RetryPolicy(**default_retry_policy(retries_cfg))
        self.executor = TaskExecutor(
            self.coordinator, default_retry=retry_policy, dry_run=dry_run
        )
        self.metrics_collector = MetricsCollector(monitoring_cfg)
        self.monitor = Monitor(monitoring_cfg, self.metrics_collector)
        self.runner = runner or PipelineRunner(
            self.executor,
            checkpoint_manager=self.checkpoint_manager,
            notifier=self.notifier,
            monitor=self.monitor,
            rollback_manager=self.rollback_manager,
            dependencies_config=dependencies_cfg,
            checkpoints_config=checkpoints_cfg,
            max_workers=max_workers,
        )
        self.recovery = RecoveryManager(
            recovery_cfg,
            checkpoint_manager=self.checkpoint_manager,
            rollback_manager=self.rollback_manager,
        )
        self.health_checker = HealthChecker(self.coordinator, monitoring_cfg)
        self.scheduler = OrchestrationScheduler(scheduler_cfg)
        self.scheduler.on_due = self._run_due
        self.planner = planner or PipelinePlanner(
            dependencies_cfg, retries_cfg, config_pipelines
        )

        self._plans: dict[str, OrchestrationPlan] = {}
        self._running = False
        self.started_at: datetime | None = None

    # ──────────────────────────────────────────────────────────────
    # Planning
    # ──────────────────────────────────────────────────────────────

    def plan(
        self,
        name: str | None = None,
        yaml_path: str | None = None,
        data: dict[str, Any] | None = None,
        description: str = "",
        schedule_mode: str | ScheduleMode = ScheduleMode.IMMEDIATE,
        scheduled_at: datetime | None = None,
        interval_seconds: float | None = None,
        max_runs: int = 0,
        depends_on: list[str] | None = None,
    ) -> OrchestrationPlan:
        """Create an orchestration plan from a pipeline.

        Exactly one of ``name`` (catalog pipeline), ``yaml_path``
        (pipeline or full plan file), or ``data`` (pipeline dict) must
        be given.

        Raises:
            InvalidPlanError: If no pipeline source is provided.
            PlanNotFoundError: If the named pipeline does not exist.
        """
        if data is not None:
            pipeline = self.planner.parse_pipeline(data)
            plan = self.planner.plan_from_pipeline(
                pipeline,
                name=name or pipeline.name,
                description=description,
                schedule_mode=schedule_mode,
                scheduled_at=scheduled_at,
                interval_seconds=interval_seconds,
                max_runs=max_runs,
                depends_on=depends_on,
            )
        elif yaml_path:
            plan = self.planner.plan_from_yaml(yaml_path)
            if name:
                plan.name = name
            if schedule_mode != ScheduleMode.IMMEDIATE:
                plan.schedule_mode = ScheduleMode(schedule_mode)
        elif name:
            pipeline = self.planner.get_pipeline(name)
            plan = self.planner.plan_from_pipeline(
                pipeline,
                name=name,
                description=description,
                schedule_mode=schedule_mode,
                scheduled_at=scheduled_at,
                interval_seconds=interval_seconds,
                max_runs=max_runs,
                depends_on=depends_on,
            )
        else:
            raise OrchestrationError("plan() requires one of: name, yaml_path, or data")

        self._plans[plan.id] = plan
        self.scheduler.register(plan)
        self.logger.info(
            "Plan %s created (pipeline=%s, mode=%s)",
            plan.id,
            plan.pipeline.name,
            plan.schedule_mode.value,
        )
        return plan

    def list_pipelines(self) -> list[str]:
        """Return the names of available pipeline catalog entries."""
        return self.planner.list_pipelines()

    def list_plans(self) -> list[OrchestrationPlan]:
        """Return all plans known to the engine."""
        return list(self._plans.values())

    # ──────────────────────────────────────────────────────────────
    # Execution
    # ──────────────────────────────────────────────────────────────

    def start(
        self, plan: OrchestrationPlan | str
    ) -> ExecutionRecord | OrchestrationPlan:
        """Start a plan.

        Immediate plans run synchronously and return an
        :class:`ExecutionRecord`; scheduled/recurring/dependency plans
        are registered with the scheduler and returned as-is.
        """
        resolved = self._resolve_plan(plan)
        if resolved.schedule_mode == ScheduleMode.IMMEDIATE:
            return self.run(resolved)
        self.scheduler.schedule(resolved)
        return resolved

    def run(
        self,
        plan: OrchestrationPlan,
        context: dict[str, Any] | None = None,
        checkpoint: Checkpoint | None = None,
    ) -> ExecutionRecord:
        """Execute a plan synchronously, with auto-recovery on failure."""
        self._mark_active()
        self.scheduler.mark_run(plan)

        result = self._execute(plan, context, checkpoint)
        state, metrics = result.state, result.metrics

        # Auto-recovery loop
        recovery_result: Any = None
        max_attempts = int(self.recovery.config.get("max_recovery_attempts", 3))
        attempts = 0
        auto = bool(self.recovery.config.get("auto_recover", False))
        while (
            state.status == PipelineStatus.FAILED
            and auto
            and self.recovery.config.get("enabled", True)
            and attempts < max_attempts
        ):
            attempts += 1
            self.logger.info(
                "Auto-recovery attempt %d/%d for plan %s",
                attempts,
                max_attempts,
                plan.id,
            )
            try:
                recovery_result, resume_checkpoint = self.recovery.recover(
                    plan,
                    state,
                    f"auto-recovery (attempt {attempts})",
                    undo_func=self._undo,
                )
            except Exception as exc:
                self.logger.error("Auto-recovery failed: %s", exc)
                break
            if not recovery_result.success:
                break
            self.metrics_collector.record_recovery()
            state.metadata["recovery_attempts"] = attempts
            state.status = PipelineStatus.RECOVERING
            state.recovered_from = resume_checkpoint.id if resume_checkpoint else None
            if self.notifier:
                self.notifier.pipeline_recovered(plan, state)
            result = self._execute(plan, context, resume_checkpoint)
            state, metrics = result.state, result.metrics

        self.state_store.save_state(state)
        record = ExecutionRecord(
            plan_id=plan.id,
            plan_name=plan.name,
            pipeline_id=plan.pipeline.id,
            state=state,
            metrics=metrics,
            rollback_plan=self.rollback_manager.get_rollback_plan(plan.id),
            recovery=recovery_result,
            events=list(state.metadata.get("events", [])),
        )
        self.state_store.record(record)

        if state.status == PipelineStatus.COMPLETED:
            self.scheduler.notify_completed(plan.id)
        return record

    def _execute(
        self,
        plan: OrchestrationPlan,
        context: dict[str, Any] | None,
        checkpoint: Checkpoint | None,
    ) -> PipelineResult:
        """Run the runner once (a single execution attempt)."""
        try:
            return self.runner.run(plan, context=context, checkpoint=checkpoint)
        except OrchestrationError as exc:
            state = ExecutionState(
                pipeline_id=plan.pipeline.id,
                plan_id=plan.id,
                status=PipelineStatus.FAILED,
                error=str(exc),
            )
            return PipelineResult(state, ExecutionMetrics(tasks_total=0))

    # ── Control operations ────────────────────────────────────────

    def resume(self, plan_id: str, checkpoint_id: str | None = None) -> ExecutionRecord:
        """Resume a plan from its latest (or named) checkpoint."""
        plan = self._get_plan(plan_id)
        checkpoint = (
            self.checkpoint_manager.restore(checkpoint_id)
            if checkpoint_id
            else self.checkpoint_manager.latest(plan.pipeline.id)
        )
        if checkpoint is None:
            raise CheckpointError(f"No checkpoint available for plan {plan_id}")
        return self.run(plan, checkpoint=checkpoint)

    def retry(self, plan_id: str) -> ExecutionRecord:
        """Re-run a plan from scratch."""
        plan = self._get_plan(plan_id)
        return self.run(plan)

    def rollback(self, plan_id: str, reason: str = "manual rollback") -> RollbackPlan:
        """Execute registered undo handlers for a plan in reverse order."""
        plan = self._get_plan(plan_id)
        if not self.rollback_manager.has_handlers():
            raise RollbackError(f"No rollback handlers registered for plan {plan_id}")
        rollback_plan = self.rollback_manager.execute_rollback(
            plan, reason, undo_func=self._undo
        )
        self.metrics_collector.record_rollback()
        self.logger.info(
            "Rollback executed for plan %s: %s",
            plan_id,
            rollback_plan.status,
        )
        return rollback_plan

    def _run_due(self, plan: OrchestrationPlan) -> None:
        """Scheduler callback: run a plan that has become due."""
        try:
            self.run(plan)
        except Exception as exc:
            self.logger.error("Due plan %s failed: %s", plan.id, exc)

    def _undo(self, task_id: str, action: str, params: dict[str, Any]) -> None:
        """Execute a rollback action for a task (undo side effects)."""
        if action == "noop":
            return
        if action == "memory.delete":
            memory = self.coordinator.engine("memory")
            memory_id = params.get("memory_id")
            if memory is None or not memory_id:
                raise EngineNotReadyError(
                    "memory", "cannot undo memory.delete without a memory id"
                )
            memory.delete(str(memory_id))
            return
        self.logger.warning(
            "No undo implementation for action %r (task %s)",
            action,
            task_id,
        )

    # ── Observability ─────────────────────────────────────────────

    def status(self, plan_id: str) -> EngineStatus:
        """Return engine status including a plan's execution state."""
        self._get_plan(plan_id)
        state = self.state_store.get_state(plan_id)
        message = (
            f"Plan {plan_id} state: {state.status.value}"
            if state
            else f"Plan {plan_id}: not executed yet"
        )
        return EngineStatus(
            name=self.name,
            version=self.version,
            running=self._running,
            started_at=self.started_at,
            health=self.health(),
            metrics=self.metrics_collector.snapshot(),
            active_plans=self._active_plan_count(),
            message=message,
        )

    def engine_status(self) -> EngineStatus:
        """Return the full engine status view."""
        return EngineStatus(
            name=self.name,
            version=self.version,
            running=self._running,
            started_at=self.started_at,
            health=self.health(),
            metrics=self.metrics_collector.snapshot(),
            active_plans=self._active_plan_count(),
            message="Enterprise Orchestration Engine operational",
        )

    def health(self) -> list[HealthStatus]:
        """Return health status for every coordinated engine."""
        return self.health_checker.check_all()

    def history(self, plan_id: str | None = None) -> list[ExecutionRecord]:
        """Return execution history (optionally filtered by plan)."""
        return self.state_store.history(plan_id)

    def checkpoints(self, pipeline_id: str | None = None) -> list[Checkpoint]:
        """Return checkpoints (optionally filtered by pipeline)."""
        if pipeline_id:
            return self.checkpoint_manager.list_for(pipeline_id)
        return self.checkpoint_manager.all()

    def get_state(self, plan_id: str) -> ExecutionState | None:
        """Return the live execution state of a plan."""
        return self.state_store.get_state(plan_id)

    # ── Engine management ─────────────────────────────────────────

    def register_engine(self, name: str, engine: Any) -> None:
        """Register an engine with the coordinator."""
        self.coordinator.register_engine(name, engine)

    def unregister_engine(self, name: str) -> bool:
        """Remove an engine from the coordinator."""
        return self.coordinator.unregister_engine(name)

    def register_handler(self, task_type: str, handler: Any) -> None:
        """Register a custom task dispatch handler."""
        self.coordinator.register_handler(task_type, handler)

    def list_handlers(self) -> list[str]:
        """Return supported task types."""
        return self.coordinator.list_handlers()

    def start_scheduler(self) -> None:
        """Start the background scheduler worker."""
        self.scheduler.start()

    def stop_scheduler(self) -> None:
        """Stop the background scheduler worker."""
        self.scheduler.stop()

    def close(self) -> None:
        """Release engine resources (stop scheduler worker)."""
        self.scheduler.stop()

    # ── Internals ─────────────────────────────────────────────────

    def _mark_active(self) -> None:
        if not self._running:
            self._running = True
            self.started_at = _utcnow()

    def _active_plan_count(self) -> int:
        return sum(
            1
            for state in self.state_store.list_states()
            if state.status in (PipelineStatus.RUNNING, PipelineStatus.RECOVERING)
        )

    def _resolve_plan(self, plan: OrchestrationPlan | str) -> OrchestrationPlan:
        if isinstance(plan, OrchestrationPlan):
            return plan
        return self._get_plan(plan)

    def _get_plan(self, plan_id: str) -> OrchestrationPlan:
        plan = self._plans.get(plan_id)
        if plan is None:
            # Fall back to name lookup
            for candidate in self._plans.values():
                if candidate.name == plan_id:
                    return candidate
        if plan is None:
            raise PlanNotFoundError(plan_id)
        return plan
