"""Pydantic models for the Enterprise Orchestration Engine.

All models use Pydantic BaseModel for validation, serialization, and
schema generation. Supports YAML, JSON, and dict formats.

Core concepts:

- :class:`Pipeline` — a declarative execution graph built from stages of tasks.
- :class:`PipelineTask` — a single unit of work dispatched to an engine.
- :class:`OrchestrationPlan` — a pipeline bound to a schedule mode.
- :class:`ExecutionState` — live state of a plan run (task statuses, results).
- :class:`Checkpoint` — a durable snapshot of execution state for recovery.
- :class:`RollbackPlan` — ordered undo steps for a failed run.
- :class:`ExecutionRecord` — the history entry for a completed run.
- :class:`EngineStatus` / :class:`HealthStatus` / :class:`ExecutionMetrics` —
  observability views of the engine.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Return current UTC timestamp (timezone-aware)."""
    return datetime.now(UTC)


def _new_id(prefix: str) -> str:
    """Generate a unique identifier with the given prefix."""
    return f"{prefix}_{uuid4().hex[:16]}"


# ──────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────


class ScheduleMode(str, Enum):
    """How an orchestration plan is triggered."""

    IMMEDIATE = "immediate"
    SCHEDULED = "scheduled"
    RECURRING = "recurring"
    DEPENDENCY = "dependency"


class StageMode(str, Enum):
    """Execution mode of a pipeline stage."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"


class TaskStatus(str, Enum):
    """Lifecycle status of a pipeline task."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class PipelineStatus(str, Enum):
    """Lifecycle status of a pipeline run."""

    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    RECOVERING = "recovering"


class RecoveryAction(str, Enum):
    """Recovery actions tried in order when a run fails."""

    CHECKPOINT_RESTORE = "checkpoint_restore"
    ROLLBACK = "rollback"
    RETRY = "retry"
    FAIL = "fail"


# ──────────────────────────────────────────────────────────────────
# Task & Pipeline definitions
# ──────────────────────────────────────────────────────────────────


class RetryPolicy(BaseModel):
    """Retry policy applied to a task on failure."""

    max_retries: int = Field(default=3, ge=0, description="Retries beyond the first")
    backoff_base_seconds: float = Field(default=1.0, ge=0.0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)
    max_backoff_seconds: float = Field(default=60.0, ge=0.0)
    timeout_seconds: float = Field(default=3600.0, gt=0.0)
    retryable_errors: list[str] = Field(
        default_factory=list, description="Exception names that may be retried"
    )

    model_config = {"extra": "forbid"}


class TaskDependency(BaseModel):
    """Enriched dependency of a task on another task."""

    task_id: str = Field(description="Id of the upstream task")
    type: str = Field(default="required", description="required | optional")
    condition: str | None = Field(
        default=None, description="Optional condition on the upstream result"
    )

    model_config = {"extra": "forbid"}


class PipelineTask(BaseModel):
    """A single unit of work in a pipeline stage.

    The task is dispatched by the coordinator to the engine named in
    ``engine`` using ``task_type`` as the operation selector.
    """

    id: str = Field(description="Unique task id within the pipeline")
    name: str = Field(default="", description="Human-readable task name")
    task_type: str = Field(description="Operation selector, e.g. 'generate'")
    engine: str = Field(default="unknown", description="Target engine name")
    params: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(
        default_factory=list, description="Ids of upstream tasks"
    )
    retry: RetryPolicy | None = Field(default=None, description="Overrides default")
    timeout_seconds: float | None = Field(default=None)
    rollback_action: str | None = Field(default=None)
    rollback_params: dict[str, Any] = Field(default_factory=dict)
    on_failure: str = Field(default="fail", description="fail | skip | continue")
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class PipelineStage(BaseModel):
    """A stage of a pipeline, executed in the declared mode."""

    id: str = Field(description="Unique stage id within the pipeline")
    name: str = Field(default="", description="Human-readable stage name")
    mode: StageMode = Field(default=StageMode.SEQUENTIAL)
    tasks: list[PipelineTask] = Field(default_factory=list)
    condition: str | None = Field(
        default=None, description="Condition evaluated before the stage runs"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class Pipeline(BaseModel):
    """A declarative pipeline: ordered stages of tasks."""

    id: str = Field(default_factory=lambda: _new_id("pipeline"))
    name: str = Field(description="Pipeline name, e.g. 'bootstrap'")
    description: str = Field(default="")
    version: str = Field(default="1.0")
    stages: list[PipelineStage] = Field(default_factory=list)
    timeout_seconds: float | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)

    model_config = {"extra": "forbid"}

    def all_tasks(self) -> list[PipelineTask]:
        """Return every task across all stages in declaration order."""
        return [task for stage in self.stages for task in stage.tasks]

    def task_map(self) -> dict[str, PipelineTask]:
        """Return task id -> task mapping across all stages."""
        return {task.id: task for task in self.all_tasks()}


class OrchestrationPlan(BaseModel):
    """A pipeline bound to a schedule mode for execution."""

    id: str = Field(default_factory=lambda: _new_id("plan"))
    name: str = Field(description="Plan name")
    description: str = Field(default="")
    pipeline: Pipeline
    schedule_mode: ScheduleMode = Field(default=ScheduleMode.IMMEDIATE)
    scheduled_at: datetime | None = Field(
        default=None, description="Trigger time for 'scheduled' mode"
    )
    interval_seconds: float | None = Field(
        default=None, description="Interval for 'recurring' mode"
    )
    max_runs: int = Field(default=0, description="Recurring run cap (0 = unlimited)")
    depends_on: list[str] = Field(
        default_factory=list, description="Plan ids for 'dependency' mode"
    )
    run_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


# ──────────────────────────────────────────────────────────────────
# Execution state & durability
# ──────────────────────────────────────────────────────────────────


class ExecutionState(BaseModel):
    """Live execution state of a plan run."""

    pipeline_id: str
    plan_id: str
    status: PipelineStatus = Field(default=PipelineStatus.PENDING)
    current_stage_id: str | None = None
    current_task_id: str | None = None
    task_statuses: dict[str, TaskStatus] = Field(default_factory=dict)
    task_results: dict[str, Any] = Field(default_factory=dict)
    task_errors: dict[str, str] = Field(default_factory=dict)
    attempts: dict[str, int] = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    correlation_id: str | None = Field(
        default=None, description="Links all events of a run"
    )
    recovered_from: str | None = Field(
        default=None, description="Checkpoint id this run recovered from"
    )
    updated_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class Checkpoint(BaseModel):
    """A durable snapshot of execution state for recovery."""

    id: str = Field(default_factory=lambda: _new_id("chk"))
    pipeline_id: str
    plan_id: str
    state: ExecutionState
    stage_index: int = Field(default=0, ge=0)
    task_index: int = Field(default=0, ge=0)
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class RollbackStep(BaseModel):
    """A single undo action in a rollback plan."""

    task_id: str
    action: str
    status: str = Field(default="pending", description="pending | executed | failed")
    error: str | None = None
    executed_at: datetime | None = None

    model_config = {"extra": "forbid"}


class RollbackPlan(BaseModel):
    """Ordered undo steps for a failed run, executed in reverse."""

    id: str = Field(default_factory=lambda: _new_id("rb"))
    pipeline_id: str
    plan_id: str
    reason: str
    steps: list[RollbackStep] = Field(default_factory=list)
    status: str = Field(default="pending", description="pending | completed | failed")
    created_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None

    model_config = {"extra": "forbid"}


class RecoveryResult(BaseModel):
    """Outcome of a recovery attempt."""

    plan_id: str
    success: bool = False
    actions_taken: list[RecoveryAction] = Field(default_factory=list)
    checkpoint_id: str | None = None
    rolled_back: list[str] = Field(default_factory=list)
    retried: list[str] = Field(default_factory=list)
    message: str = Field(default="")
    recovered_at: datetime = Field(default_factory=_utcnow)

    model_config = {"extra": "forbid"}


# ──────────────────────────────────────────────────────────────────
# Observability
# ──────────────────────────────────────────────────────────────────


class HealthStatus(BaseModel):
    """Health of a single engine component."""

    engine: str
    healthy: bool
    message: str = Field(default="")
    checked_at: datetime = Field(default_factory=_utcnow)
    details: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class ExecutionMetrics(BaseModel):
    """Aggregate counters for a plan run or the whole engine."""

    tasks_total: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_skipped: int = 0
    retries_total: int = 0
    checkpoints_created: int = 0
    rollbacks_executed: int = 0
    recoveries_performed: int = 0
    duration_seconds: float = 0.0
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"extra": "forbid"}


class EngineStatus(BaseModel):
    """Full status view of the orchestration engine."""

    name: str = Field(default="Enterprise Orchestration Engine")
    version: str = Field(default="1.0")
    running: bool = False
    started_at: datetime | None = None
    health: list[HealthStatus] = Field(default_factory=list)
    metrics: ExecutionMetrics = Field(default_factory=ExecutionMetrics)
    active_plans: int = Field(default=0)
    message: str = Field(default="")

    model_config = {"extra": "forbid"}


class ExecutionRecord(BaseModel):
    """History record for a plan run."""

    record_id: str = Field(default_factory=lambda: _new_id("rec"))
    plan_id: str
    plan_name: str = Field(default="")
    pipeline_id: str
    state: ExecutionState
    metrics: ExecutionMetrics = Field(default_factory=ExecutionMetrics)
    rollback_plan: RollbackPlan | None = None
    recovery: RecoveryResult | None = None
    events: list[str] = Field(default_factory=list)
    recorded_at: datetime = Field(default_factory=_utcnow)

    model_config = {"extra": "forbid"}
