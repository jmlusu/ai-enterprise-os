"""Exceptions for the Enterprise Orchestration Engine.

Hierarchy:

- :class:`OrchestrationError` — base for all orchestration failures.
- :class:`InvalidPlanError` — declarative plan/pipeline is malformed.
- :class:`DependencyError` — dependency graph has cycles or missing ids.
- :class:`TaskExecutionError` — a task failed at the target engine.
- :class:`PipelineExecutionError` — a pipeline run failed.
- :class:`SchedulerError` — scheduling/schedule-mode problems.
- :class:`CheckpointError` — checkpoint save/restore problems.
- :class:`RollbackError` — rollback execution problems.
- :class:`RecoveryError` — recovery attempt problems.
- :class:`EngineNotReadyError` — a required engine is unavailable.
- :class:`PlanNotFoundError` — no plan/record with the given id.
"""

from __future__ import annotations

from typing import Any


class OrchestrationError(Exception):
    """Base class for all orchestration engine errors."""


class InvalidPlanError(OrchestrationError):
    """Raised when a declarative plan or pipeline definition is invalid."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class DependencyError(OrchestrationError):
    """Raised when the dependency graph cannot be resolved."""

    def __init__(self, message: str, cycle: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.cycle = cycle or []


class TaskExecutionError(OrchestrationError):
    """Raised when a pipeline task fails at the target engine."""

    def __init__(
        self,
        task_id: str,
        task_type: str,
        engine: str,
        cause: str,
        attempts: int = 1,
    ) -> None:
        super().__init__(
            f"Task {task_id!r} ({task_type} on {engine}) failed after "
            f"{attempts} attempt(s): {cause}"
        )
        self.task_id = task_id
        self.task_type = task_type
        self.engine = engine
        self.cause = cause
        self.attempts = attempts


class PipelineExecutionError(OrchestrationError):
    """Raised when a pipeline run fails."""

    def __init__(self, pipeline_id: str, task_id: str | None, cause: str) -> None:
        super().__init__(f"Pipeline {pipeline_id!r} failed at {task_id}: {cause}")
        self.pipeline_id = pipeline_id
        self.task_id = task_id
        self.cause = cause


class SchedulerError(OrchestrationError):
    """Raised for scheduling problems."""


class CheckpointError(OrchestrationError):
    """Raised when a checkpoint cannot be saved or restored."""


class RollbackError(OrchestrationError):
    """Raised when rollback execution fails."""


class RecoveryError(OrchestrationError):
    """Raised when a recovery attempt fails."""


class EngineNotReadyError(OrchestrationError):
    """Raised when a required engine is missing or not available."""

    def __init__(self, engine: str, detail: str = "not registered") -> None:
        super().__init__(f"Engine {engine!r} {detail}")
        self.engine = engine
        self.detail = detail


class PlanNotFoundError(OrchestrationError):
    """Raised when a plan or execution record does not exist."""

    def __init__(self, plan_id: str) -> None:
        super().__init__(f"Plan not found: {plan_id}")
        self.plan_id = plan_id
