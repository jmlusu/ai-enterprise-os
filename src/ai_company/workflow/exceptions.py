"""Exceptions for workflow engine."""

from __future__ import annotations

from typing import Any


class WorkflowError(Exception):
    """Base exception for workflow errors."""

    def __init__(
        self,
        message: str,
        workflow_id: str | None = None,
        execution_id: str | None = None,
    ):
        super().__init__(message)
        self.workflow_id = workflow_id
        self.execution_id = execution_id


class WorkflowNotFoundError(WorkflowError):
    """Workflow definition not found."""


class WorkflowValidationError(WorkflowError):
    """Workflow definition validation failed."""


class InvalidStateError(WorkflowError):
    """Invalid state transition attempted."""


class StateNotFoundError(WorkflowError):
    """State not found in workflow definition."""


class TransitionError(WorkflowError):
    """State transition failed."""


class ApprovalRequiredError(WorkflowError):
    """Approval required but not provided."""


class ApprovalTimeoutError(WorkflowError):
    """Approval request timed out."""


class ApprovalRejectedError(WorkflowError):
    """Approval was rejected."""

    def __init__(self, message: str, reason: str = "", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.reason = reason


class ExecutionNotFoundError(WorkflowError):
    """Workflow execution not found."""


class ExecutionNotRunningError(WorkflowError):
    """Execution is not in running state."""


class ExecutionAlreadyCompletedError(WorkflowError):
    """Execution already completed."""


class ContextError(WorkflowError):
    """Workflow context error."""


class ContextNotFoundError(WorkflowError):
    """Execution context not found."""


class ActionError(WorkflowError):
    """Action execution error."""


class ActionTimeoutError(ActionError):
    """Action execution timed out."""


class ActionNotFoundError(ActionError):
    """Action handler not found."""


class WaitError(WorkflowError):
    """Wait state error."""


class WaitTimeoutError(WaitError):
    """Wait condition timed out."""


class ConditionEvaluationError(WorkflowError):
    """Condition evaluation failed."""


class DataValidationError(WorkflowError):
    """Workflow data validation failed."""


class SchedulerError(WorkflowError):
    """Scheduler error."""


class RegistryError(WorkflowError):
    """Workflow registry error."""


class HandlerError(WorkflowError):
    """Handler execution error."""


class RetryExhaustedError(WorkflowError):
    """All retries exhausted."""

    def __init__(self, message: str, attempts: int, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.attempts = attempts


class ConcurrentModificationError(WorkflowError):
    """Concurrent modification of execution context."""
