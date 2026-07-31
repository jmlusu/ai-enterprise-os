"""Pipeline execution runtime.

The :class:`PipelineRunner` executes a pipeline stage by stage:

- ``sequential`` stages run tasks in dependency (topological) order.
- ``parallel`` stages run dependency-ready task groups concurrently.
- ``conditional`` stages evaluate a condition before running.

Throughout execution the runner:

- maintains the :class:`ExecutionState` (task statuses/results),
- publishes ``pipeline.*`` / ``task.*`` events via the notifier,
- records metrics via the monitor,
- writes checkpoints after completed tasks,
- registers rollback handlers for tasks that declare undo actions,
- applies each task's ``on_failure`` policy (fail | skip | continue).
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

from ai_company.orchestration.dependencies import DependencyGraph
from ai_company.orchestration.exceptions import (
    PipelineExecutionError,
    TaskExecutionError,
)
from ai_company.orchestration.executor import TaskExecutor, TaskResult
from ai_company.orchestration.lifecycle import transition_pipeline, transition_task
from ai_company.orchestration.models import (
    Checkpoint,
    ExecutionMetrics,
    ExecutionState,
    OrchestrationPlan,
    PipelineStatus,
    StageMode,
    TaskStatus,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _resolve_path(path: str, data: dict[str, Any]) -> Any:
    """Resolve a dotted path against a nested dict."""
    value: Any = data
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit():
            index = int(part)
            value = value[index] if index < len(value) else None
        else:
            return None
    return value


def evaluate_condition(
    expression: str | None,
    results: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> bool:
    """Evaluate a simple condition expression against task results.

    Supported forms (safe subset, no Python eval):

    - ``true`` / ``false`` / ``yes`` / ``no`` — boolean literals
    - ``path`` — truthiness of a resolved value
    - ``path == value`` / ``path != value`` / ``path in [a, b]``
    - ``path >= n`` / ``path <= n`` / ``path > n`` / ``path < n``

    ``path`` is a dotted path into the task-results map, e.g.
    ``load_registry.success`` or ``generate_all.created_files``.
    """
    if expression is None or not expression.strip():
        return True

    expr = expression.strip()

    # Boolean literals
    lowered = expr.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False

    # in [a, b, ...] membership
    if " in [" in expr and expr.endswith("]"):
        head, _, tail = expr.partition(" in [")
        values = [v.strip().strip("'\"").strip() for v in tail[:-1].split(",")]
        value = _resolve_path(head.strip(), results)
        return value in values

    # Comparisons
    for op in ("==", "!=", ">=", "<=", ">", "<"):
        if op in expr:
            head, _, tail = expr.partition(op)
            left = _resolve_path(head.strip(), results)
            right: Any = tail.strip().strip("'\"")
            if right.lower() in {"true", "false", "yes", "no", "null", "none"}:
                right = {
                    "true": True,
                    "false": False,
                    "yes": True,
                    "no": False,
                    "null": None,
                    "none": None,
                }[right.lower()]
            else:
                try:
                    right = float(right)
                    if right.is_integer():
                        right = int(right)
                except ValueError:
                    pass
            try:
                if op == "==":
                    return left == right
                if op == "!=":
                    return left != right
                if op == ">=":
                    return bool(left is not None and left >= right)
                if op == "<=":
                    return bool(left is not None and left <= right)
                if op == ">":
                    return bool(left is not None and left > right)
                if op == "<":
                    return bool(left is not None and left < right)
            except TypeError:
                return False

    # Bare path -> task completion / truthiness
    value = _resolve_path(expr, results)
    if value is None:
        return False
    return bool(value)


class PipelineResult:
    """Outcome of a pipeline run."""

    def __init__(
        self,
        state: ExecutionState,
        metrics: ExecutionMetrics,
    ) -> None:
        self.state = state
        self.metrics = metrics

    @property
    def success(self) -> bool:
        return self.state.status == PipelineStatus.COMPLETED

    @property
    def status(self) -> PipelineStatus:
        return self.state.status


class PipelineRunner:
    """Executes an :class:`OrchestrationPlan` against its tasks."""

    def __init__(
        self,
        executor: TaskExecutor,
        checkpoint_manager: Any | None = None,
        notifier: Any | None = None,
        monitor: Any | None = None,
        rollback_manager: Any | None = None,
        dependencies_config: dict[str, Any] | None = None,
        checkpoints_config: dict[str, Any] | None = None,
        max_workers: int = 4,
        logger: logging.Logger | None = None,
    ) -> None:
        self.executor = executor
        self.checkpoint_manager = checkpoint_manager
        self.notifier = notifier
        self.monitor = monitor
        self.rollback_manager = rollback_manager
        self.dependencies_config = dependencies_config or {}
        self.checkpoints_config = checkpoints_config or {}
        self.max_workers = max(1, max_workers)
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._stage_index = 0
        self._task_index = 0

    # ── Public API ────────────────────────────────────────────────

    def run(
        self,
        plan: OrchestrationPlan,
        context: dict[str, Any] | None = None,
        checkpoint: Checkpoint | None = None,
    ) -> PipelineResult:
        """Execute a plan, optionally resuming from a checkpoint."""
        start = time.time()

        if checkpoint is not None:
            state = checkpoint.state.model_copy(deep=True)
            if state.status != PipelineStatus.RUNNING:
                state.status = transition_pipeline(state.status, PipelineStatus.RUNNING)
            stage_index = checkpoint.stage_index
            self._stage_index = stage_index
            self.logger.info(
                "Resuming plan %s from checkpoint %s (stage %d)",
                plan.id,
                checkpoint.id,
                stage_index,
            )
        else:
            state = ExecutionState(
                pipeline_id=plan.pipeline.id,
                plan_id=plan.id,
                correlation_id=(context.get("correlation_id") if context else None),
            )
            state.task_statuses = {
                task.id: TaskStatus.PENDING for task in plan.pipeline.all_tasks()
            }
            state.status = transition_pipeline(
                PipelineStatus.PENDING, PipelineStatus.RUNNING
            )
            state.started_at = state.updated_at
            stage_index = 0
            self._stage_index = 0

        run_context: dict[str, Any] = {
            "plan": plan,
            "pipeline": plan.pipeline,
            "state": state,
            "results": state.task_results,
            "correlation_id": state.correlation_id,
            **(context or {}),
        }

        metrics = ExecutionMetrics(
            started_at=state.started_at,
            tasks_total=len(plan.pipeline.all_tasks()),
        )
        if self.monitor:
            self.monitor.on_pipeline_started(plan, state)
        if self.notifier:
            self.notifier.pipeline_started(plan, state)

        try:
            stages = plan.pipeline.stages
            for index in range(stage_index, len(stages)):
                stage = stages[index]
                state.current_stage_id = stage.id
                state.updated_at = _utcnow()
                self.logger.info(
                    "Plan %s: executing stage %s (%s)",
                    plan.id,
                    stage.id,
                    stage.mode.value,
                )
                self._execute_stage(plan, stage, state, run_context, metrics)
                self._stage_index = index + 1

                if self.checkpoint_manager and self._stage_checkpoint_enabled():
                    self._write_checkpoint(plan, state, run_context, metrics)

            state.current_stage_id = None
            state.current_task_id = None
            state.status = transition_pipeline(state.status, PipelineStatus.COMPLETED)
            state.completed_at = _utcnow()
            state.updated_at = state.completed_at
            metrics.completed_at = state.completed_at
            metrics.duration_seconds = time.time() - start
            self.logger.info("Plan %s completed", plan.id)
        except PipelineExecutionError as exc:
            self._fail(plan, state, metrics, start, str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            self._fail(plan, state, metrics, start, f"{type(exc).__name__}: {exc}")

        if self.monitor:
            self.monitor.on_pipeline_finished(plan, state, metrics)
        if self.notifier:
            if state.status == PipelineStatus.COMPLETED:
                self.notifier.pipeline_completed(plan, state, metrics)
            elif state.status == PipelineStatus.FAILED:
                self.notifier.pipeline_failed(plan, state)

        return PipelineResult(state, metrics)

    # ── Stage execution ───────────────────────────────────────────

    def _execute_stage(
        self,
        plan: OrchestrationPlan,
        stage: Any,
        state: ExecutionState,
        run_context: dict[str, Any],
        metrics: ExecutionMetrics,
    ) -> None:
        """Execute one stage according to its mode."""
        graph = DependencyGraph(plan.pipeline, self.dependencies_config)

        # Conditional gate
        if stage.mode == StageMode.CONDITIONAL:
            if stage.condition and not evaluate_condition(
                stage.condition, state.task_results, run_context
            ):
                self.logger.info("Stage %s condition not met — skipping", stage.id)
                for task in stage.tasks:
                    if state.task_statuses.get(task.id) in (
                        None,
                        TaskStatus.PENDING,
                    ):
                        state.task_statuses[task.id] = TaskStatus.SKIPPED
                        metrics.tasks_skipped += 1
                        if self.notifier:
                            self.notifier.task_skipped(plan, state, task.id)
                return
        elif stage.condition and not evaluate_condition(
            stage.condition, state.task_results, run_context
        ):
            self.logger.info("Stage %s condition not met — skipping", stage.id)
            for task in stage.tasks:
                if state.task_statuses.get(task.id) in (
                    None,
                    TaskStatus.PENDING,
                ):
                    state.task_statuses[task.id] = TaskStatus.SKIPPED
                    metrics.tasks_skipped += 1
                    if self.notifier:
                        self.notifier.task_skipped(plan, state, task.id)
            return

        if stage.mode == StageMode.PARALLEL:
            self._execute_parallel(plan, stage, graph, state, run_context, metrics)
        else:
            self._execute_sequential(plan, stage, graph, state, run_context, metrics)

    def _execute_sequential(
        self,
        plan: OrchestrationPlan,
        stage: Any,
        graph: DependencyGraph,
        state: ExecutionState,
        run_context: dict[str, Any],
        metrics: ExecutionMetrics,
    ) -> None:
        """Run the stage's tasks in dependency (topological) order."""
        task_index = 0
        for task in stage.tasks:
            self._task_index = task_index
            status = state.task_statuses.get(task.id, TaskStatus.PENDING)
            if status == TaskStatus.COMPLETED:
                task_index += 1
                continue
            if status in (TaskStatus.SKIPPED, TaskStatus.CANCELLED):
                task_index += 1
                continue
            if status == TaskStatus.FAILED and task.on_failure == "fail":
                task_index += 1
                continue

            completed = {
                tid
                for tid, st in state.task_statuses.items()
                if st == TaskStatus.COMPLETED
            }
            failed = {
                tid
                for tid, st in state.task_statuses.items()
                if st == TaskStatus.FAILED
            }
            if task.id not in graph.ready_tasks(completed, failed):
                self._mark_skipped(plan, state, task.id, metrics)
                task_index += 1
                continue

            state.current_task_id = task.id
            result = self._run_task(plan, task, state, run_context, metrics)
            self._apply_task_result(plan, task, state, result, metrics)
            task_index += 1

            if result.status == "failed" and task.on_failure == "fail":
                self._write_checkpoint(plan, state, run_context, metrics)
                raise PipelineExecutionError(
                    plan.pipeline.id,
                    task.id,
                    result.error or "unknown task failure",
                )

    def _execute_parallel(
        self,
        plan: OrchestrationPlan,
        stage: Any,
        graph: DependencyGraph,
        state: ExecutionState,
        run_context: dict[str, Any],
        metrics: ExecutionMetrics,
    ) -> None:
        """Run dependency-ready task groups concurrently."""
        stage_task_ids = {task.id for task in stage.tasks}
        max_workers = min(
            self.max_workers,
            int(self.dependencies_config.get("max_parallel_tasks", 4)),
        )

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            while True:
                completed = {
                    tid
                    for tid, st in state.task_statuses.items()
                    if st == TaskStatus.COMPLETED
                }
                ready = [
                    tid
                    for tid in graph.ready_tasks(completed)
                    if tid in stage_task_ids
                    and state.task_statuses.get(tid, TaskStatus.PENDING)
                    == TaskStatus.PENDING
                ]
                if not ready:
                    break

                futures = {
                    pool.submit(
                        self._run_task, plan, task, state, run_context, metrics
                    ): task
                    for task in stage.tasks
                    if task.id in ready
                }
                for future in as_completed(futures):
                    task = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:  # defensive
                        result = TaskResult(
                            task_id=task.id,
                            status="failed",
                            error=f"{type(exc).__name__}: {exc}",
                        )
                    self._apply_task_result(plan, task, state, result, metrics)
                    if result.status == "failed" and task.on_failure == "fail":
                        for other in futures:
                            other.cancel()
                        raise PipelineExecutionError(
                            plan.pipeline.id,
                            task.id,
                            result.error or "unknown task failure",
                        )

    def _run_task(
        self,
        plan: OrchestrationPlan,
        task: Any,
        state: ExecutionState,
        run_context: dict[str, Any],
        metrics: ExecutionMetrics,
    ) -> TaskResult:
        """Run a single task through the executor."""
        state.current_task_id = task.id
        state.task_statuses[task.id] = transition_task(
            state.task_statuses.get(task.id, TaskStatus.PENDING),
            TaskStatus.RUNNING,
        )
        state.attempts[task.id] = state.attempts.get(task.id, 0) + 1
        if self.notifier:
            self.notifier.task_started(plan, state, task.id)
        if self.monitor:
            self.monitor.on_task_started(plan, state, task.id)

        try:
            return self.executor.execute_task(task, run_context)
        except TaskExecutionError as exc:
            return TaskResult(
                task_id=task.id,
                status="failed",
                error=exc.cause,
                attempts=exc.attempts,
                retried=exc.attempts > 1,
            )

    def _apply_task_result(
        self,
        plan: OrchestrationPlan,
        task: Any,
        state: ExecutionState,
        result: TaskResult,
        metrics: ExecutionMetrics,
    ) -> None:
        """Merge a TaskResult into the execution state."""
        if result.status == "completed":
            state.task_statuses[task.id] = transition_task(
                TaskStatus.RUNNING, TaskStatus.COMPLETED
            )
            state.task_results[task.id] = result.output or {}
            if task.rollback_action and self.rollback_manager:
                self.rollback_manager.register_handler(
                    task.id, task.rollback_action, task.rollback_params
                )
            metrics.tasks_completed += 1
            if result.retried:
                metrics.retries_total += result.attempts - 1
            if self.notifier:
                self.notifier.task_completed(plan, state, task.id, result)
            if self.monitor:
                self.monitor.on_task_finished(plan, state, task.id, result)
            if self._task_checkpoint_enabled(metrics):
                self._write_checkpoint(plan, state, run_context={}, metrics=metrics)

        elif result.status == "failed":
            state.task_statuses[task.id] = transition_task(
                TaskStatus.RUNNING, TaskStatus.FAILED
            )
            state.task_errors[task.id] = result.error or "unknown error"
            metrics.tasks_failed += 1
            if result.retried:
                metrics.retries_total += result.attempts - 1
            if self.notifier:
                self.notifier.task_failed(plan, state, task.id, result)
            if self.monitor:
                self.monitor.on_task_finished(plan, state, task.id, result)

        else:  # skipped
            state.task_statuses[task.id] = TaskStatus.SKIPPED
            metrics.tasks_skipped += 1
            if self.notifier:
                self.notifier.task_skipped(plan, state, task.id)

    def _mark_skipped(
        self,
        plan: OrchestrationPlan,
        state: ExecutionState,
        task_id: str,
        metrics: ExecutionMetrics,
    ) -> None:
        """Mark a task skipped (unresolvable dependency)."""
        state.task_statuses[task_id] = TaskStatus.SKIPPED
        metrics.tasks_skipped += 1
        if self.notifier:
            self.notifier.task_skipped(plan, state, task_id)

    # ── Checkpoints ───────────────────────────────────────────────

    def _stage_checkpoint_enabled(self) -> bool:
        return bool(
            self.checkpoints_config.get("auto_checkpoint_on_stage_completed", True)
        )

    def _task_checkpoint_enabled(self, metrics: ExecutionMetrics) -> bool:
        if not self.checkpoints_config.get("auto_checkpoint_on_task_completed", True):
            return False
        interval = int(self.checkpoints_config.get("interval_tasks", 1))
        completed = metrics.tasks_completed
        return interval <= 0 or completed % interval == 0

    def _write_checkpoint(
        self,
        plan: OrchestrationPlan,
        state: ExecutionState,
        run_context: dict[str, Any],
        metrics: ExecutionMetrics,
    ) -> None:
        if not self.checkpoint_manager:
            return
        if not self.checkpoints_config.get("enabled", True):
            return
        try:
            self.checkpoint_manager.create(
                plan=plan,
                state=state,
                stage_index=self._stage_index,
                task_index=self._task_index,
                context={
                    k: v
                    for k, v in run_context.items()
                    if k not in {"plan", "pipeline", "state"}
                },
            )
            metrics.checkpoints_created += 1
        except Exception as exc:  # checkpoint failures are non-fatal
            self.logger.warning("Checkpoint write failed: %s", exc)

    # ── Failure handling ──────────────────────────────────────────

    def _fail(
        self,
        plan: OrchestrationPlan,
        state: ExecutionState,
        metrics: ExecutionMetrics,
        start: float,
        error: str,
    ) -> None:
        state.status = transition_pipeline(state.status, PipelineStatus.FAILED)
        state.error = error
        state.completed_at = _utcnow()
        state.updated_at = state.completed_at
        metrics.completed_at = state.completed_at
        metrics.duration_seconds = time.time() - start
        self.logger.error("Plan %s failed: %s", plan.id, error)
